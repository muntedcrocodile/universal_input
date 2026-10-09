# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Keep selections attached to text when Markdown changes its representation."""
from difflib import SequenceMatcher


def map_selection(source, target, anchor, position):
    """Map Qt UTF-16 offsets through shared text, snapping removed syntax nearby."""
    if source == target:
        return anchor, position
    matches = SequenceMatcher(None, source, target, autojunk=False).get_matching_blocks()
    matches = [match for match in matches if match.size]

    def map_offset(offset, prefer_right):
        index = len(source.encode('utf-16-le')[:offset * 2].decode('utf-16-le', errors='surrogatepass'))
        if prefer_right is None:
            # At a word's end stay before closing Markdown markers; at its
            # start stay after opening markers, ready to continue typing.
            prefer_right = index == 0 or source[index - 1].isspace()
        candidates = []
        for start, destination, length in matches:
            nearest = min(max(index, start), start + length)
            candidates.append((abs(index - nearest), destination + nearest - start))
        if candidates:
            distance = min(item[0] for item in candidates)
            boundaries = [item[1] for item in candidates if item[0] == distance]
            mapped = max(boundaries) if prefer_right else min(boundaries)
        else:
            mapped = min(index, len(target))
        return len(target[:mapped].encode('utf-16-le')) // 2

    if anchor == position:
        mapped = map_offset(position, None)
        return mapped, mapped
    return (map_offset(anchor, anchor < position),
            map_offset(position, position < anchor))
