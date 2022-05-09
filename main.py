from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from binance_api import Binance
from aiogram import Bot, types
import pandas as pd
import threading
import psycopg2
import math
import time
import os


db_postgres = psycopg2.connect(os.environ['DATABASE_URL'], sslmode="require")
cursor = db_postgres.cursor()
cursor.execute("SELECT Value FROM Parameters where Parameter = 'API_KEY'")
API_KEY = cursor.fetchone()[0]
cursor.execute("SELECT Value FROM Parameters where Parameter = 'API_SECRET'")
API_SECRET = cursor.fetchone()[0]

bot = Binance(API_KEY=str(API_KEY), API_SECRET=str(API_SECRET))

bot_tg = Bot(os.environ['BOT_TOKEN'])
dp = Dispatcher(bot_tg, storage=MemoryStorage())

def get_change(current, previous):
    check = []
    check.append(current)
    check.append(previous)
    check = pd.Series(check)
    return round(check.pct_change()[1], 4)

def MA_back_in_future(summ, last_110):
    MA = 0
    last_110 = last_110[-(summ+1):]
    last_110 = last_110[:-1]
    for sv in last_110:
        MA += float(sv[4])
    return MA / summ

def MA_calc(summ, last_110):
    MA = 0
    last_110 = last_110[-summ:]
    for sv in last_110:
        MA += float(sv[4])
    return MA/summ

def tp_and_sl(procent, plus, price):
    if plus == '+':
        x = price
        x = x + ((x/100) * procent)
        return round(x, 2)
    if plus == '-':
        x = price
        x = x - ((x/100) * procent)
        return round(x, 2)

def open_order_short(quantity, TP, SL):
    bot.futuresCreateOrder(
        symbol='BTCUSDT',
        side='SELL',
        type='MARKET',
        recvWindow=5000,
        quantity =quantity)
    prices = float(bot.futuresSymbolPriceTicker(symbol='BTCUSDT')['price'])
    time.sleep(3)
    bot.futuresCreateOrder(
        symbol='BTCUSDT',
        side='BUY',
        positionSide='BOTH',
        type='TAKE_PROFIT_MARKET',
        stopPrice=tp_and_sl(TP, '-', price=prices),
        closePosition=True,
        timeInForce='GTE_GTC',
        workingType='MARK_PRICE',
        priceProtect=True)
    bot.futuresCreateOrder(
        symbol='BTCUSDT',
        side='BUY',
        positionSide='BOTH',
        type='STOP_MARKET',
        stopPrice=tp_and_sl(SL, '+', price=prices),
        closePosition=True,
        timeInForce='GTE_GTC',
        workingType='MARK_PRICE',
        priceProtect=True)
    time.sleep(3)

def open_order_long(quantity, TP, SL):

    bot.futuresCreateOrder(
        symbol='BTCUSDT',
        side='BUY',
        type='MARKET',
        recvWindow=5000,
        quantity =quantity)

    prices = float(bot.futuresSymbolPriceTicker(symbol='BTCUSDT')['price'])
    time.sleep(3)
    bot.futuresCreateOrder(
        symbol='BTCUSDT',
        side='SELL',
        positionSide='BOTH',
        type='TAKE_PROFIT_MARKET',
        stopPrice=tp_and_sl(TP, '+', price=prices),
        closePosition=True,
        timeInForce='GTE_GTC',
        workingType='MARK_PRICE',
        priceProtect=True)
    bot.futuresCreateOrder(
        symbol='BTCUSDT',
        side='SELL',
        positionSide='BOTH',
        type='STOP_MARKET',
        stopPrice=tp_and_sl(SL, '-', price=prices),
        closePosition=True,
        timeInForce='GTE_GTC',
        workingType='MARK_PRICE',
        priceProtect=True)
    time.sleep(3)

def threading_main():
    db_postgres = psycopg2.connect(os.environ['DATABASE_URL'], sslmode="require")
    cursor = db_postgres.cursor()
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'SELL_SHORT_MA'")
    SELL_SHORT_MA = int(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'SELL_LONG_MA'")
    SELL_LONG_MA = int(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'BUY_SHORT_MA'")
    BUY_SHORT_MA = int(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'BUY_LONG_MA'")
    BUY_LONG_MA = int(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'QUANTITY_BTC'")
    QUANTITY_BTC = float(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'PERCENT_DIF_MA'")
    PERCENT_DIF_MA = float(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'TP_BUY'")
    TP_BUY = float(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'SL_BUY'")
    SL_BUY = float(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'TP_SELL'")
    TP_SELL = float(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'SL_BUY'")
    SL_SELL = float(cursor.fetchone()[0])
    cursor.execute("SELECT Value FROM Parameters where Parameter = 'TIMEFRAME'")
    TIMEFRAME = str(cursor.fetchone()[0])

    limit = max(SELL_LONG_MA, BUY_LONG_MA) + 10
    while True:
        try:
            cursor.execute("SELECT Value FROM Parameters where Parameter = 'WORK'")
            WORK = int(cursor.fetchone()[0])
            if WORK == 1:
                last_110MA = bot.futuresKlines(symbol='BTCUSDT', interval=TIMEFRAME, limit=limit)
                Present = get_change(math.floor(MA_calc(SELL_LONG_MA, last_110MA)),
                                     math.floor(MA_calc(SELL_SHORT_MA, last_110MA)))
                Past = get_change(math.floor(MA_back_in_future(SELL_LONG_MA, last_110MA)),
                                  math.floor(MA_back_in_future(SELL_SHORT_MA, last_110MA)))
                positions = float([i for i in bot.futuresAccount()['positions'] if i['symbol'] == 'BTCUSDT'][0]['entryPrice'])
                if Present <= PERCENT_DIF_MA and Present > 0 and Past > PERCENT_DIF_MA and positions == 0:
                    try:
                        open_order_short(quantity = QUANTITY_BTC, TP = TP_SELL, SL = SL_SELL)
                    except:
                        pass

                Present = get_change(math.floor(MA_calc(BUY_SHORT_MA, last_110MA)),
                                     math.floor(MA_calc(BUY_LONG_MA, last_110MA)))
                Past = get_change(math.floor(MA_back_in_future(BUY_SHORT_MA, last_110MA)),
                                  math.floor(MA_back_in_future(BUY_LONG_MA, last_110MA)))
                positions = float([i for i in bot.futuresAccount()['positions'] if i['symbol'] == 'BTCUSDT'][0]['entryPrice'])
                if Present <= PERCENT_DIF_MA and Present > 0 and Past > PERCENT_DIF_MA and positions == 0:
                    try:
                        open_order_long(quantity = QUANTITY_BTC, TP = TP_BUY, SL = SL_BUY)
                    except:
                        pass
            else:
                break
        except:
            pass
        time.sleep(15)

@dp.message_handler(content_types=['text'])
async def get_text_messages(msg: types.Message):
    db_postgres = psycopg2.connect(os.environ['DATABASE_URL'], sslmode="require")
    cursor = db_postgres.cursor()
    if msg.text.lower() == 'старт' and msg.from_user.id == 431679317:
        Keyboard = ReplyKeyboardMarkup(resize_keyboard=True).\
            row(KeyboardButton('старт 🟢'), KeyboardButton('стоп')).\
            row(KeyboardButton('Изменить параметры'), KeyboardButton('Посмотреть параметры'))
        await msg.answer(f'{msg.from_user.first_name} все под контролем 👌, работаем.', reply_markup=Keyboard)
        cursor.execute(f"UPDATE Parameters SET Value = '1' WHERE Parameter = 'WORK'")
        db_postgres.commit()
        threading.Thread(target=threading_main).start()

    if msg.text.lower() == 'стоп' and msg.from_user.id == 431679317:
        Keyboard = ReplyKeyboardMarkup(resize_keyboard=True).\
            row(KeyboardButton('старт'), KeyboardButton('стоп 🔴')).\
            row(KeyboardButton('Изменить параметры'), KeyboardButton('Посмотреть параметры'))
        await msg.answer(f'{msg.from_user.last_name} остановил открытие новых сделок!', reply_markup=Keyboard)
        cursor.execute(f"UPDATE Parameters SET Value = '0' WHERE Parameter = 'WORK'")
        db_postgres.commit()

    if msg.text.lower() == 'посмотреть параметры' and msg.from_user.id == 431679317:
        cursor.execute('SELECT * FROM Parameters')
        param = cursor.fetchall()
        if param[0][1].strip() != "":
            APIKEY = "Есть"
        else:
            APIKEY = "Нет"
        if param[1][1].strip() != "":
            APISECRET = "Есть"
        else:
            APISECRET = "Нет"

        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(types.InlineKeyboardButton(text=f"{param[0][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{APIKEY}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[1][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{APISECRET}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[2][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{int(param[2][1].strip())}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[3][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{int(param[3][1].strip())}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[4][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{int(param[4][1].strip())}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[5][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{int(param[5][1].strip())}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[6][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{param[6][1].strip()}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[7][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{param[7][1].strip()}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[8][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{param[8][1].strip()}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[9][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{param[9][1].strip()}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[10][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{param[10][1].strip()}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[11][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{param[11][1].strip()}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[12][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{param[12][1].strip()}", callback_data=f"НУЖНО"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[13][0].strip()}", callback_data=f"НУЖНО"),types.InlineKeyboardButton(text=f"{param[13][1].strip()}", callback_data=f"НУЖНО"))
        await msg.answer('ИНФО (НЕ КЛИКАБЕЛЬНО КЛИКАЙТЕ 😂)', reply_markup=keyboard)

    if msg.text.lower() == 'изменить параметры' and msg.from_user.id == 431679317:
        cursor.execute('SELECT * FROM Parameters')
        param = cursor.fetchall()

        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(types.InlineKeyboardButton(text=f"{param[0][0].strip()}", callback_data=f"{param[0][0].strip()}"),
                     types.InlineKeyboardButton(text=f"{param[1][0].strip()}", callback_data=f"{param[1][0].strip()}"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[2][0].strip()}", callback_data=f"{param[2][0].strip()}"),
                     types.InlineKeyboardButton(text=f"{param[3][0].strip()}", callback_data=f"{param[3][0].strip()}"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[4][0].strip()}", callback_data=f"{param[4][0].strip()}"),
                     types.InlineKeyboardButton(text=f"{param[5][0].strip()}", callback_data=f"{param[5][0].strip()}"))
        keyboard.add(types.InlineKeyboardButton(text=f"{param[6][0].strip()}", callback_data=f"{param[6][0].strip()}"))
        keyboard.add(types.InlineKeyboardButton(text=f"{param[7][0].strip()}", callback_data=f"{param[7][0].strip()}"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[8][0].strip()}", callback_data=f"{param[8][0].strip()}"),
                     types.InlineKeyboardButton(text=f"{param[9][0].strip()}", callback_data=f"{param[9][0].strip()}"))
        keyboard.row(types.InlineKeyboardButton(text=f"{param[10][0].strip()}", callback_data=f"{param[10][0].strip()}"),
                     types.InlineKeyboardButton(text=f"{param[11][0].strip()}", callback_data=f"{param[11][0].strip()}"))
        keyboard.add(types.InlineKeyboardButton(text=f"{param[12][0].strip()}", callback_data=f"{param[12][0].strip()}"))

        await msg.answer("Выбери что нужно изменить:", reply_markup=keyboard)

        @dp.callback_query_handler(text=f"API_KEY")
        async def cmd_dialog(message: types.Message):
            class Mydialog6(StatesGroup):
                otvet = State()
            await Mydialog6.otvet.set()
            await message.answer(f"Введи новое значение {param[0][0].strip()}")
            @dp.message_handler(state=Mydialog6.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'API_KEY'")
                db_postgres.commit()
                await message.answer(f"Изменено на: {user_message}")
                await state.finish()

        @dp.callback_query_handler(text=f"API_SECRET")
        async def cmd_dialog(message: types.Message):
            class Mydialog5(StatesGroup):
                otvet = State()
            await Mydialog5.otvet.set()
            await message.answer(f"Введи новое значение {param[1][0].strip()}")
            @dp.message_handler(state=Mydialog5.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'API_SECRET'")
                db_postgres.commit()
                await message.answer(f"Изменено на: {user_message}")
                await state.finish()

        @dp.callback_query_handler(text=f"SELL_SHORT_MA")
        async def cmd_dialog(message: types.Message):
            class Mydialog4(StatesGroup):
                otvet = State()
            await Mydialog4.otvet.set()
            await message.answer(f"Введи новое значение {param[2][0].strip()}")
            @dp.message_handler(state=Mydialog4.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'SELL_SHORT_MA'")
                db_postgres.commit()
                await message.answer(f"Изменено на: {user_message}")
                await state.finish()

        @dp.callback_query_handler(text=f"SELL_LONG_MA")
        async def cmd_dialog(message: types.Message):
            class Mydialog3(StatesGroup):
                otvet = State()
            await Mydialog3.otvet.set()
            await message.answer(f"Введи новое значение {param[3][0].strip()}")
            @dp.message_handler(state=Mydialog3.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'SELL_LONG_MA'")
                db_postgres.commit()
                await message.answer(f"Изменено на: {user_message}")
                await state.finish()

        @dp.callback_query_handler(text=f"BUY_SHORT_MA")
        async def cmd_dialog(message: types.Message):
            class Mydialog2(StatesGroup):
                otvet = State()
            await Mydialog2.otvet.set()
            await message.answer(f"Введи новое значение {param[4][0].strip()}")
            @dp.message_handler(state=Mydialog2.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'BUY_SHORT_MA'")
                db_postgres.commit()
                await message.answer(f"Изменено на: {user_message}")
                await state.finish()

        @dp.callback_query_handler(text=f"BUY_LONG_MA")
        async def cmd_dialog(message: types.Message):
            class Mydialog1(StatesGroup):
                otvet = State()
            await Mydialog1.otvet.set()
            await message.answer(f"Введи новое значение {param[5][0].strip()}")
            @dp.message_handler(state=Mydialog1.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                    cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'BUY_LONG_MA'")
                    db_postgres.commit()

                    await message.answer(f"Изменено на: {user_message}")

                await state.finish()

        @dp.callback_query_handler(text=f"QUANTITY_BTC")
        async def cmd_dialog(message: types.Message):
            class Mydialog7(StatesGroup):
                otvet = State()
            await Mydialog7.otvet.set()
            await message.answer(f"Введи новое значение {param[6][0].strip()}")
            @dp.message_handler(state=Mydialog7.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                    cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'QUANTITY_BTC'")
                    db_postgres.commit()

                    await message.answer(f"Изменено на: {user_message}")

                await state.finish()

        @dp.callback_query_handler(text=f"PERCENT_DIF_MA")
        async def cmd_dialog(message: types.Message):
            class Mydialog8(StatesGroup):
                otvet = State()
            await Mydialog8.otvet.set()
            await message.answer(f"Введи новое значение {param[7][0].strip()}")
            @dp.message_handler(state=Mydialog8.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                    cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'PERCENT_DIF_MA'")
                    db_postgres.commit()

                    await message.answer(f"Изменено на: {user_message}")

                await state.finish()

        @dp.callback_query_handler(text=f"TP_BUY")
        async def cmd_dialog(message: types.Message):
            class Mydialog9(StatesGroup):
                otvet = State()
            await Mydialog9.otvet.set()
            await message.answer(f"Введи новое значение {param[8][0].strip()}")
            @dp.message_handler(state=Mydialog9.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                    cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'TP_BUY'")
                    db_postgres.commit()

                    await message.answer(f"Изменено на: {user_message}")

                await state.finish()

        @dp.callback_query_handler(text=f"SL_BUY")
        async def cmd_dialog(message: types.Message):
            class Mydialog10(StatesGroup):
                otvet = State()
            await Mydialog10.otvet.set()
            await message.answer(f"Введи новое значение {param[9][0].strip()}")
            @dp.message_handler(state=Mydialog10.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                    cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'SL_BUY'")
                    db_postgres.commit()

                    await message.answer(f"Изменено на: {user_message}")

                await state.finish()

        @dp.callback_query_handler(text=f"TP_SELL")
        async def cmd_dialog(message: types.Message):
            class Mydialog11(StatesGroup):
                otvet = State()
            await Mydialog11.otvet.set()
            await message.answer(f"Введи новое значение {param[10][0].strip()}")
            @dp.message_handler(state=Mydialog11.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                    cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'TP_SELL'")
                    db_postgres.commit()

                    await message.answer(f"Изменено на: {user_message}")

                await state.finish()

        @dp.callback_query_handler(text=f"SL_SELL")
        async def cmd_dialog(message: types.Message):
            class Mydialog12(StatesGroup):
                otvet = State()
            await Mydialog12.otvet.set()
            await message.answer(f"Введи новое значение {param[11][0].strip()}")
            @dp.message_handler(state=Mydialog12.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                    cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'SL_SELL'")
                    db_postgres.commit()

                    await message.answer(f"Изменено на: {user_message}")

                await state.finish()

        @dp.callback_query_handler(text=f"TIMEFRAME")
        async def cmd_dialog(message: types.Message):
            class Mydialog13(StatesGroup):
                otvet = State()
            await Mydialog13.otvet.set()
            await message.answer(f"Введи новое значение {param[12][0].strip()}")
            @dp.message_handler(state=Mydialog13.otvet)
            async def process_message(message: types.Message, state: FSMContext):
                async with state.proxy() as data:
                    data['text'] = message.text
                    user_message = data['text']
                    cursor.execute(f"UPDATE Parameters SET Value = '{user_message}' WHERE Parameter = 'TIMEFRAME'")
                    db_postgres.commit()

                    await message.answer(f"Изменено на: {user_message}")

                await state.finish()

executor.start_polling(dp)