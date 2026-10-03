from aiogram import Dispatcher, F, types

from services.knowledge import get_method_assets


def register_method_assets(
    dp: Dispatcher,
    admin_ids: list[int],
):

    @dp.message(F.text == "/мой_метод")
    async def show_method_assets(
        message: types.Message,
    ):

        if message.from_user.id not in admin_ids:
            return

        assets = await get_method_assets()

        if not assets:
            await message.answer(
                "📚 В твоём методе пока нет элементов."
            )
            return

        for asset in assets:

            (
                asset_id,
                proposal_id,
                asset_type,
                title,
                content,
                version,
                created_at,
            ) = asset

            await message.answer(
                (
                    f"📚 Элемент метода #{asset_id}\n\n"
                    f"Тип: {asset_type}\n"
                    f"Версия: {version}\n\n"
                    f"{title}\n\n"
                    f"{content}"
                )
            )
