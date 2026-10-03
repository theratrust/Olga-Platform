import re

with open("bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# Ensure the callback query handler for answers catches all 'q_ans_' callbacks correctly
old_callback_handler = '''@dp.callback_query(Quiz.QUESTION_STEP, F.data.startswith("q_ans_"))
async def process_question_answer(callback: types.CallbackQuery, state: FSMContext):'''

new_callback_handler = '''@dp.callback_query(F.data.startswith("q_ans_"))
async def process_question_answer(callback: types.CallbackQuery, state: FSMContext):'''

if old_callback_handler in code:
    code = code.replace(old_callback_handler, new_callback_handler)
    with open("bot.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("Successfully patched quiz callback handler in bot.py")
else:
    print("Callback handler pattern already updated or structured differently.")
