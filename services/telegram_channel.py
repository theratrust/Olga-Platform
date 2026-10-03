from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class TelegramChannel:

    def __init__(self, bot, channel_id):
        self.bot = bot
        self.channel_id = channel_id

    async def send_post(self, text, buttons=None):

        markup = None

        if buttons:
            keyboard = []

            for row in buttons:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            b["text"],
                            url=b.get("url")
                        )
                        for b in row
                    ]
                )

            markup = InlineKeyboardMarkup(keyboard)

        msg = await self.bot.send_message(
            chat_id=self.channel_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup
        )

        return msg.message_id

    async def edit_post(self, message_id, text, buttons=None):

        markup = None

        if buttons:
            keyboard = []

            for row in buttons:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            b["text"],
                            url=b.get("url")
                        )
                        for b in row
                    ]
                )

            markup = InlineKeyboardMarkup(keyboard)

        await self.bot.edit_message_text(
            chat_id=self.channel_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup
        )
