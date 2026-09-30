import re

from pyrogram import enums, errors, types

from BOMMYMUSIC.misc import db
from BOMMYMUSIC.utils.database import get_lang
from BOMMYMUSIC.utils.formatters import seconds_to_min, time_to_seconds
from strings import get_string

_TAG_RE = re.compile(
    r"<(/?)(b|a)(?:\s+href=([^>]+))?>",
    re.IGNORECASE,
)

_consumed = set()

_FORBIDDEN = (
    errors.ChatSendPhotosForbidden,
    errors.ChatSendMediaForbidden,
)


async def _lang(chat_id):
    return get_string(await get_lang(chat_id))


def _parse_inline(segment):
    parts = []
    stack = []
    pos = 0

    for m in _TAG_RE.finditer(segment):
        if m.start() > pos:
            parts.append(segment[pos:m.start()])

        pos = m.end()

        closing = m.group(1)
        tag = m.group(2).lower()
        href = m.group(3)

        if not closing:
            stack.append(
                (
                    tag,
                    href.strip("\"'") if href else None,
                    len(parts),
                )
            )

        elif stack and stack[-1][0] == tag:
            open_tag, url, start = stack.pop()

            inner = parts[start:]
            del parts[start:]

            if len(inner) == 1:
                inner = inner[0]
            elif not inner:
                inner = ""

            if open_tag == "b":
                parts.append(
                    types.RichTextBold(
                        text=inner
                    )
                )
            else:
                parts.append(
                    types.RichTextUrl(
                        text=inner,
                        url=url,
                    )
                )

    if pos < len(segment):
        parts.append(segment[pos:])

    if not parts:
        return ""

    return (
        parts[0]
        if len(parts) == 1
        else parts
    )


def _balance_lines(caption_html):
    lines = []
    carry = False

    for line in caption_html.split("\n"):
        if not line:
            lines.append(line)
            continue

        if carry:
            line = "<b>" + line

        opened = len(
            re.findall(
                r"<b>",
                line,
                re.IGNORECASE,
            )
        )

        closed = len(
            re.findall(
                r"</b>",
                line,
                re.IGNORECASE,
            )
        )

        carry = opened > closed

        if carry:
            line += "</b>"

        lines.append(line)

    return lines


def _html_caption_to_blocks(caption_html):
    return [
        types.InputRichBlockParagraph(
            text=_parse_inline(line)
        )
        for line in _balance_lines(
            caption_html
        )
    ]


# ============================================================
# ✦ BOMMY MUSIC — AURORA PLAYER
# ============================================================


def _frame(played):
    try:
        tick = int(
            time_to_seconds(played)
        )
    except (
        TypeError,
        ValueError,
    ):
        tick = 0

    hearts = (
        "♡",
        "♥",
        "💗",
        "💖",
        "💞",
        "💖",
        "💗",
        "♥",
    )

    waves = (
        "▁▂▃▄▅▆▅▄",
        "▂▃▄▅▆▇▆▅",
        "▃▄▅▆▇▆▅▄",
        "▄▅▆▇▆▅▄▃",
        "▅▆▇▆▅▄▃▂",
        "▆▇▆▅▄▃▂▁",
        "▇▆▅▄▃▂▁▂",
        "▆▅▄▃▂▁▂▃",
    )

    aurora = (
        "✦",
        "✧",
        "⋆",
        "✦",
        "✧",
        "⋆",
    )

    return (
        hearts[tick % len(hearts)],
        waves[tick % len(waves)],
        aurora[tick % len(aurora)],
    )


def _progress(played, dur):
    try:
        current = time_to_seconds(
            played
        )

        total = time_to_seconds(
            dur
        )

    except (
        TypeError,
        ValueError,
    ):
        current = 0
        total = 0

    ratio = (
        current / total
        if total
        else 0
    )

    ratio = max(
        0,
        min(1, ratio),
    )

    slots = 22

    pos = min(
        slots - 1,
        int(
            ratio
            * (slots - 1)
        ),
    )

    heart, wave, spark = _frame(
        played
    )

    rail = (
        "━" * pos
        + heart
        + "━"
        * (
            slots
            - pos
            - 1
        )
    )

    return (
        f"<b>{played}</b>  "
        f"{rail}  "
        f"<b>{dur}</b>\n"
        f"          "
        f"{spark}  ♫ "
        f"{wave} ♫  "
        f"{spark}"
    )


def _header(
    playing,
    played=None,
):
    if played:
        (
            heart,
            wave,
            spark,
        ) = _frame(played)

    else:
        heart = "💗"
        wave = "▁▂▃▄▅▆▅▄"
        spark = "✦"

    if playing:
        return (
            f"╭────────────── "
            f"{spark} {heart} {spark} "
            f"──────────────╮\n"
            f"│   "
            f"<b>BOMMY ♪ MUSIC</b>"
            f"   •   "
            f"<b>AURORA</b>"
            f"   │\n"
            f"│   {heart}  "
            f"<b>NOW PLAYING</b>"
            f"   ♫ {wave}   │\n"
            f"╰────────────────────────"
            f"────────────────────╯"
        )

    return (
        "╭────────────── ♡ ──────────────╮\n"
        "│   <b>BOMMY ♪ MUSIC</b>"
        "   •   <b>PAUSED</b>   │\n"
        "│   ♡  <b>READY TO RESUME</b>"
        "          │\n"
        "╰───────────────────────────────╯"
    )


def _control_rows(
    _,
    chat_id,
    playing,
):
    queue_count = max(
        len(db.get(chat_id) or [])
        - 1,
        0,
    )

    queue_label = _[
        "RICH_BTN_QUEUE"
    ].format(
        queue_count
    )

    toggle = (
        "❚❚  "
        + _["RICH_BTN_PAUSE"]
        if playing
        else
        "▶  "
        + _["RICH_BTN_RESUME"]
    )

    return [

        # MAIN CONTROLS
        types.InputRichBlockButtons(
            buttons=[

                types.RichMessageButton(
                    text=(
                        "↻  "
                        + _[
                            "RICH_BTN_REPLAY"
                        ]
                    ),
                    style=(
                        enums.ButtonStyle
                        .DANGER
                    ),
                    callback_data=(
                        f"ADMIN Replay|"
                        f"{chat_id}"
                    ),
                ),

                types.RichMessageButton(
                    text=toggle,
                    style=(
                        enums.ButtonStyle
                        .SUCCESS
                    ),
                    callback_data=(
                        f"ADMIN "
                        f"{'Pause' if playing else 'Resume'}"
                        f"|{chat_id}"
                    ),
                ),

                types.RichMessageButton(
                    text="NEXT  »",
                    style=(
                        enums.ButtonStyle
                        .PRIMARY
                    ),
                    callback_data=(
                        f"ADMIN Skip|"
                        f"{chat_id}"
                    ),
                ),
            ]
        ),

        # QUEUE
        types.InputRichBlockButtons(
            buttons=[

                types.RichMessageButton(
                    text=(
                        f"♡  "
                        f"{queue_label}"
                        f"  ·  "
                        f"{queue_count}"
                        f" TRACKS"
                    ),
                    style=(
                        enums.ButtonStyle
                        .DEFAULT
                    ),
                    callback_data=(
                        f"nowplaying_queue "
                        f"{chat_id}"
                    ),
                ),
            ]
        ),
    ]


def _progress_row(
    played,
    dur,
):
    return types.InputRichBlockButtons(
        buttons=[
            types.RichMessageButton(
                text=_progress(
                    played,
                    dur,
                ),
                style=(
                    enums.ButtonStyle
                    .DEFAULT
                ),
                callback_data="GetTimer",
            )
        ]
    )


def build_now_playing_blocks(
    _,
    photo,
    caption_html,
    chat_id,
    played=None,
    dur=None,
    playing=True,
):
    blocks = [

        types.InputRichBlockPhoto(
            photo=types.InputMediaPhoto(
                photo
            )
        ),

        types.InputRichBlockParagraph(
            text=_parse_inline(
                _header(
                    playing,
                    played,
                )
            )
        ),
    ]

    blocks += (
        _html_caption_to_blocks(
            caption_html
        )
    )

    if played and dur:
        blocks.append(
            _progress_row(
                played,
                dur,
            )
        )

    blocks += _control_rows(
        _,
        chat_id,
        playing,
    )

    return blocks


def _message_key(message):
    return (
        message.chat.id,
        message.id,
    )


def _strip_photo(blocks):
    return [
        b
        for b in blocks
        if not isinstance(
            b,
            types.InputRichBlockPhoto,
        )
    ]


async def _edit_rich(
    message,
    blocks,
):
    try:
        return await message.edit_text(
            rich_message=(
                types.InputRichMessage(
                    blocks=blocks
                )
            )
        )

    except _FORBIDDEN:
        plain = _strip_photo(
            blocks
        )

        if len(plain) == len(blocks):
            raise

        return await message.edit_text(
            rich_message=(
                types.InputRichMessage(
                    blocks=plain
                )
            )
        )


async def _try_deliver(
    client,
    target_chat_id,
    blocks,
    replace,
):
    rich = types.InputRichMessage(
        blocks=blocks
    )

    if replace is not None:
        try:
            edited = await replace.edit_text(
                rich_message=rich
            )

        except _FORBIDDEN:
            raise

        except Exception:
            try:
                await replace.delete()
            except Exception:
                pass

        else:
            _consumed.add(
                _message_key(
                    replace
                )
            )

            return (
                edited
                or replace
            )

    return await client.send_rich_message(
        target_chat_id,
        rich_message=rich,
    )


async def _deliver(
    client,
    target_chat_id,
    blocks,
    replace=None,
):
    try:
        return await _try_deliver(
            client,
            target_chat_id,
            blocks,
            replace,
        )

    except _FORBIDDEN:
        plain = _strip_photo(
            blocks
        )

        if len(plain) == len(blocks):
            raise

        return await _try_deliver(
            client,
            target_chat_id,
            plain,
            replace,
        )


def caption_blocks(
    caption_html
):
    return _html_caption_to_blocks(
        caption_html
    )


async def edit_rich(
    message,
    blocks,
):
    return await _edit_rich(
        message,
        blocks,
    )


async def deliver_rich(
    client,
    target_chat_id,
    blocks,
    replace=None,
):
    result = await _deliver(
        client,
        target_chat_id,
        blocks,
        replace,
    )

    if replace is not None:
        _consumed.discard(
            _message_key(
                replace
            )
        )

    return result


async def release_mystic(
    mystic
):
    if mystic is None:
        return

    key = _message_key(
        mystic
    )

    if key in _consumed:
        _consumed.discard(key)
        return

    try:
        await mystic.delete()
    except Exception:
        pass


async def send_now_playing_rich(
    client,
    chat_id,
    target_chat_id,
    photo,
    caption_html,
    replace=None,
):
    _ = await _lang(
        chat_id
    )

    blocks = build_now_playing_blocks(
        _,
        photo,
        caption_html,
        chat_id,
    )

    msg = await _deliver(
        client,
        target_chat_id,
        blocks,
        replace,
    )

    if db.get(chat_id):
        db[chat_id][0][
            "np_photo"
        ] = photo

        db[chat_id][0][
            "np_caption"
        ] = caption_html

    return msg


# ============================================================
# 📋 QUEUE PLAYER
# ============================================================


def build_queue_blocks(
    _,
    caption_html,
    chat_id,
    qid,
):
    blocks = _html_caption_to_blocks(
        caption_html
    )

    blocks.append(
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=(
                        "▶  "
                        + _[
                            "RICH_BTN_PLAYNOW"
                        ]
                    ),
                    style=(
                        enums.ButtonStyle
                        .SUCCESS
                    ),
                    callback_data=(
                        f"ADMIN PlayNow|"
                        f"{chat_id}_{qid}"
                    ),
                )
            ]
        )
    )

    blocks.append(
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=(
                        "NEXT  »  "
                        + _[
                            "RICH_BTN_SKIP"
                        ]
                    ),
                    style=(
                        enums.ButtonStyle
                        .PRIMARY
                    ),
                    callback_data=(
                        f"ADMIN Skip|"
                        f"{chat_id}"
                    ),
                ),

                types.RichMessageButton(
                    text=(
                        "■  "
                        + _[
                            "RICH_BTN_END"
                        ]
                    ),
                    style=(
                        enums.ButtonStyle
                        .DANGER
                    ),
                    callback_data=(
                        f"ADMIN Stop|"
                        f"{chat_id}"
                    ),
                ),
            ]
        )
    )

    return blocks


# ============================================================
# IMPORTANT:
# queue.py imports this function.
# ============================================================


def build_queue_list_blocks(
    _,
    tracks,
    chat_id,
    cplay="g",
):
    """
    Premium BOMMY MUSIC queue dashboard.

    This function is required by:
    BOMMYMUSIC/plugins/tools/queue.py
    """

    blocks = [

        types.InputRichBlockParagraph(
            text=_parse_inline(
                "<b>"
                "◈ ʙᴏᴍᴍʏ ᴍᴜsɪᴄ"
                "  •  "
                "ǫᴜᴇᴜᴇ ᴅᴀsʜʙᴏᴀʀᴅ"
                "</b>"
            )
        ),
    ]

    # No tracks
    if not tracks:
        blocks.append(
            types.InputRichBlockParagraph(
                text=_parse_inline(
                    "<b>"
                    "♡ ǫᴜᴇᴜᴇ ɪs ᴇᴍᴘᴛʏ"
                    "</b>"
                )
            )
        )

    else:

        # CURRENT TRACK
        current = tracks[0]

        current_title = str(
            current.get(
                "title",
                "Unknown",
            )
        )[:46]

        current_dur = current.get(
            "dur",
            "--:--",
        )

        current_by = str(
            current.get(
                "by",
                "Unknown",
            )
        )[:28]

        blocks.append(
            types.InputRichBlockParagraph(
                text=_parse_inline(
                    f"<b>"
                    f"● ɴᴏᴡ ᴘʟᴀʏɪɴɢ"
                    f"</b>\n"
                    f"♡ <b>"
                    f"{current_title}"
                    f"</b>\n"
                    f"⌁ {current_dur}"
                    f"  ·  "
                    f"♫ {current_by}"
                )
            )
        )

        # UPCOMING
        queued = tracks[1:]

        if not queued:

            blocks.append(
                types.InputRichBlockParagraph(
                    text=_parse_inline(
                        "<b>"
                        "╰─ ǫᴜᴇᴜᴇ ᴇᴍᴘᴛʏ"
                        "</b>"
                    )
                )
            )

        else:

            blocks.append(
                types.InputRichBlockParagraph(
                    text=_parse_inline(
                        "<b>"
                        "╭─ ᴜᴘᴄᴏᴍɪɴɢ ᴛʀᴀᴄᴋs ─╮"
                        "</b>"
                    )
                )
            )

            for index, track in enumerate(
                queued[:12],
                start=1,
            ):
                title = str(
                    track.get(
                        "title",
                        "Unknown",
                    )
                )[:48]

                dur = track.get(
                    "dur",
                    "--:--",
                )

                by = str(
                    track.get(
                        "by",
                        "Unknown",
                    )
                )[:28]

                marker = (
                    "◉"
                    if index == 1
                    else "•"
                )

                blocks.append(
                    types.InputRichBlockParagraph(
                        text=_parse_inline(
                            f"<b>"
                            f"{marker} "
                            f"{index:02d}  "
                            f"{title}"
                            f"</b>\n"
                            f"   ◷ {dur}"
                            f"  ·  "
                            f"♫ {by}"
                        )
                    )
                )

            remaining = (
                len(queued) - 12
            )

            if remaining > 0:
                blocks.append(
                    types.InputRichBlockParagraph(
                        text=_parse_inline(
                            f"＋ "
                            f"{remaining} "
                            f"more tracks"
                        )
                    )
                )

    # QUEUE / PLAYER BUTTONS
    queued_count = max(
        len(tracks) - 1,
        0,
    )

    blocks.append(
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=(
                        f"☰ ǫᴜᴇᴜᴇ"
                        f" · "
                        f"{queued_count}"
                    ),
                    style=(
                        enums.ButtonStyle
                        .PRIMARY
                    ),
                    callback_data=(
                        f"nowplaying_queue "
                        f"{chat_id}"
                    ),
                ),

                types.RichMessageButton(
                    text="↩ ᴘʟᴀʏᴇʀ",
                    style=(
                        enums.ButtonStyle
                        .DEFAULT
                    ),
                    callback_data=(
                        f"queue_back_timer "
                        f"{cplay}"
                    ),
                ),
            ]
        )
    )

    # SKIP / END
    blocks.append(
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_[
                        "RICH_BTN_SKIP"
                    ],
                    style=(
                        enums.ButtonStyle
                        .SUCCESS
                    ),
                    callback_data=(
                        f"ADMIN Skip|"
                        f"{chat_id}"
                    ),
                ),

                types.RichMessageButton(
                    text=_[
                        "RICH_BTN_END"
                    ],
                    style=(
                        enums.ButtonStyle
                        .DANGER
                    ),
                    callback_data=(
                        f"ADMIN Stop|"
                        f"{chat_id}"
                    ),
                ),
            ]
        )
    )

    return blocks


async def send_queue_rich(
    client,
    chat_id,
    target_chat_id,
    caption_html,
    qid,
    replace=None,
):
    _ = await _lang(
        chat_id
    )

    blocks = build_queue_blocks(
        _,
        caption_html,
        chat_id,
        qid,
    )

    return await _deliver(
        client,
        target_chat_id,
        blocks,
        replace,
    )


# ============================================================
# ⏱ LIVE PLAYER UPDATE
# ============================================================


async def update_now_playing_progress(
    mystic,
    chat_id,
    played,
    dur,
    playing=True,
):
    info = db.get(
        chat_id
    )

    if not info:
        return None

    photo = info[0].get(
        "np_photo"
    )

    caption_html = info[0].get(
        "np_caption"
    )

    if (
        not photo
        or not caption_html
    ):
        return None

    _ = await _lang(
        chat_id
    )

    blocks = build_now_playing_blocks(
        _,
        photo,
        caption_html,
        chat_id,
        played,
        dur,
        playing,
    )

    return await _edit_rich(
        mystic,
        blocks,
    )


# ============================================================
# ⏯ PLAYER STATE
# ============================================================


async def set_now_playing_state(
    chat_id,
    playing,
):
    info = db.get(
        chat_id
    )

    if not info:
        return None

    mystic = info[0].get(
        "mystic"
    )

    photo = info[0].get(
        "np_photo"
    )

    caption_html = info[0].get(
        "np_caption"
    )

    if (
        not mystic
        or not photo
        or not caption_html
    ):
        return None

    played = (
        seconds_to_min(
            info[0].get(
                "played",
                0,
            )
        )
        or None
    )

    dur = info[0].get(
        "dur"
    )

    _ = await _lang(
        chat_id
    )

    blocks = build_now_playing_blocks(
        _,
        photo,
        caption_html,
        chat_id,
        played,
        dur,
        playing,
    )

    try:
        return await _edit_rich(
            mystic,
            blocks,
        )

    except Exception:
        return None
