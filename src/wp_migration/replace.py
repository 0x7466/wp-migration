import re

_SERIALIZED_HEAD_BYTES = re.compile(rb's:(\d+):("|\\")')


def replace_in_string(text: str, old: str, new: str) -> str:
    if not text or old not in text:
        return text

    old_bytes = old.encode("utf-8")
    new_bytes = new.encode("utf-8")
    text_bytes = text.encode("utf-8")

    result = bytearray()
    pos = 0

    while pos < len(text_bytes):
        m = _SERIALIZED_HEAD_BYTES.search(text_bytes, pos)
        if not m:
            remaining = text_bytes[pos:]
            if old_bytes in remaining:
                remaining = remaining.replace(old_bytes, new_bytes)
            result.extend(remaining)
            break

        before = text_bytes[pos : m.start()]
        if old_bytes in before:
            before = before.replace(old_bytes, new_bytes)
        result.extend(before)

        length = int(m.group(1))
        opening_escaped = m.group(2) == b'\\"'
        content_start = m.end()
        content_end = content_start + length
        content_bytes = text_bytes[content_start:content_end]

        closing_size = 3 if opening_escaped else 2
        serialized_end = content_end + closing_size

        if old_bytes in content_bytes:
            new_content = content_bytes.replace(old_bytes, new_bytes)
            new_length = len(new_content)
            if opening_escaped:
                result.extend(f's:{new_length}:\\"'.encode("utf-8"))
                result.extend(new_content)
                result.extend(b'\\";')
            else:
                result.extend(f's:{new_length}:"'.encode("utf-8"))
                result.extend(new_content)
                result.extend(b'";')
        else:
            result.extend(text_bytes[m.start() : serialized_end])

        pos = serialized_end

    return result.decode("utf-8")


def replace_in_sql(sql: str, old: str, new: str) -> str:
    return replace_in_string(sql, old, new)
