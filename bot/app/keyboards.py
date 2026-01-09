from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def reopen_hide_keyboard(title_id: int, episode_id: int | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if episode_id is None:
        reopen_payload = f"reopen:{title_id}"
    else:
        reopen_payload = f"reopen:{title_id}:{episode_id}"
    builder.button(text="Вернуться", callback_data=reopen_payload)
    builder.button(text="Скрыть", callback_data="hide")
    builder.adjust(2)
    return builder.as_markup()


def refresh_keyboard(variant_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Обновить", callback_data=f"refresh:{variant_id}")
    builder.button(text="Скрыть", callback_data="hide")
    builder.adjust(1, 1)
    return builder.as_markup()


def series_keyboard(title_id: int, episode_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅ Назад", callback_data=f"prev_ep:{title_id}:{episode_id}")
    builder.button(text="➡ Вперёд", callback_data=f"next_ep:{title_id}:{episode_id}")
    builder.button(text="Серии", callback_data=f"episodes:{title_id}")
    builder.button(text="Озвучка", callback_data=f"aud_menu:{title_id}:{episode_id}")
    builder.button(text="Качество", callback_data=f"q_menu:{title_id}:{episode_id}")
    builder.button(text="⭐", callback_data=f"toggle_fav:{title_id}")
    builder.button(text="🔔", callback_data=f"toggle_sub:{title_id}")
    builder.button(text="Premium", callback_data="open_premium")
    builder.button(text="Скрыть", callback_data="hide")
    builder.adjust(2, 1, 2, 2, 2)
    return builder.as_markup()


def movie_keyboard(title_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Озвучка", callback_data=f"aud_menu:{title_id}")
    builder.button(text="Качество", callback_data=f"q_menu:{title_id}")
    builder.button(text="⭐", callback_data=f"toggle_fav:{title_id}")
    builder.button(text="Premium", callback_data="open_premium")
    builder.button(text="Скрыть", callback_data="hide")
    builder.adjust(2, 1, 2)
    return builder.as_markup()


def audio_menu_keyboard(
    title_id: int,
    episode_id: int | None,
    audio_options: list[tuple[int, str]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for audio_id, name in audio_options:
        if episode_id is None:
            callback = f"aud_set:{title_id}:{audio_id}"
        else:
            callback = f"aud_set:{title_id}:{episode_id}:{audio_id}"
        builder.button(text=name, callback_data=callback)
    builder.button(text="Назад", callback_data=_back_payload(title_id, episode_id))
    builder.button(text="Скрыть", callback_data="hide")
    builder.adjust(1)
    return builder.as_markup()


def quality_menu_keyboard(
    title_id: int,
    episode_id: int | None,
    quality_options: list[tuple[int, str]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for quality_id, name in quality_options:
        if episode_id is None:
            callback = f"q_set:{title_id}:{quality_id}"
        else:
            callback = f"q_set:{title_id}:{episode_id}:{quality_id}"
        builder.button(text=name, callback_data=callback)
    builder.button(text="Назад", callback_data=_back_payload(title_id, episode_id))
    builder.button(text="Скрыть", callback_data="hide")
    builder.adjust(1)
    return builder.as_markup()


def _back_payload(title_id: int, episode_id: int | None) -> str:
    if episode_id is None:
        return f"back_main:{title_id}"
    return f"back_main:{title_id}:{episode_id}"
