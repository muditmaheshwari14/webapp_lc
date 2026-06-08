import re


POINT_STRUCTURED_CODES = {"45A", "46A", "47A", "71D", "78", "72Z"}
EXPANDED_POINT_ROW_CODES = {"46A", "47A"}
FIELD_CODE_WITH_POINT_PATTERN = re.compile(r"^([0-9]{2}[A-Z]?)(\d+)?$")
POINT_MARKER_PATTERN = re.compile(
    r"""
    (?m)
    (?<!\S)
    (?P<prefix>[+*]?)
    \s*
    (?P<number>\d{1,2})
    (?P<delimiter>[.)-])
    (?=\s|[A-Za-z])
    """,
    re.VERBOSE,
)
LEADING_POINT_MARKER_PATTERN = re.compile(
    r"^\s*[+*]?\s*(\d{1,2})\s*[.)-]\s*",
)


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_classification_lines(value: str) -> str:
    lines = []
    for line in value.splitlines():
        if "Classification:" in line:
            continue
        lines.append(line.strip())
    return "\n".join(lines).strip()


def remove_dot_separator_lines(value: str) -> str:
    lines = []
    for line in value.splitlines():
        stripped = line.strip()
        if stripped == ".":
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def remove_leading_field_label(code: str, value: str) -> str:
    known_prefixes = {
        "27": ("Sequence Of Total",),
        "40A": ("Form of Documentary Credit",),
        "20": ("Documentary Credit Number",),
        "31C": ("Date Of Issue",),
        "40E": ("Applicable Rules",),
        "31D": ("Date and Place of Expiry",),
        "51A": ("Applicant Bank",),
        "51D": ("Initializing Institution (Name and Address)",),
        "50": ("Applicant",),
        "59": ("Beneficiary",),
        "32B": ("Currency Code, Amount",),
        "39A": ("Percentage Credit Amount Tolerance",),
        "41D": ("Available With ... By ...", "Available With... By..."),
        "42C": ("Drafts At", "Drafts at"),
        "42A": ("Drawee",),
        "42D": ("Drawee", "Drawee (Name and Address)"),
        "43P": ("Partial Shipments",),
        "43T": ("Transhipment",),
        "44E": ("Port of Loading/Airport of Departure",),
        "44F": ("Port of Discharge/Airport of Destination",),
        "44C": ("Latest Date of Shipment",),
        "45A": ("Description of Goods and/or Services",),
        "46A": ("Documents Required",),
        "47A": ("Additional Conditions",),
        "71D": ("Details of Charges", "Charges"),
        "48": ("Period For Presentation in Days", "Period for Presentation"),
        "49": ("Confirmation Instructions",),
        "78": ("Instructions to the Paying/Accepting/Negotiating Bank",),
        "72Z": ("Sender to Receiver Information / Additional Narrative",),
    }

    prefixes = known_prefixes.get(get_base_field_code(code), ())
    if not prefixes:
        return value.strip()

    normalized_value = " ".join(value.split())
    for prefix in prefixes:
        normalized_prefix = " ".join(prefix.split())
        if normalized_value.lower().startswith(normalized_prefix.lower()):
            trimmed = normalized_value[len(normalized_prefix):].strip(" :.-")
            trimmed = re.sub(
                r"^\(\s*NAME\s+AND\s+ADDRESS\s*\)\s*",
                "",
                trimmed,
                flags=re.IGNORECASE,
            )
            return trimmed

    return value.strip()


def normalize_general_value(value: str) -> str:
    lines = [line.strip() for line in value.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def get_base_field_code(code: str) -> str:
    if not code:
        return ""

    normalized_code = str(code).strip()
    match = FIELD_CODE_WITH_POINT_PATTERN.fullmatch(normalized_code)
    if match:
        return match.group(1)

    return normalized_code


def should_expand_field_rows(code: str) -> bool:
    return get_base_field_code(code) in EXPANDED_POINT_ROW_CODES


def _is_line_start(text: str, position: int) -> bool:
    line_start = text.rfind("\n", 0, position) + 1
    return not text[line_start:position].strip()


def _find_point_candidates(text: str):
    candidates = []

    for match in POINT_MARKER_PATTERN.finditer(text):
        marker_start = match.start()
        prefix = match.group("prefix") or ""

        candidates.append(
            {
                "start": marker_start,
                "number": int(match.group("number")),
                "prefix": prefix,
                "delimiter": match.group("delimiter"),
                "line_start": _is_line_start(text, marker_start),
            }
        )

    return candidates


def _candidate_modes(candidates):
    modes = []
    explicit_prefixes = sorted({candidate["prefix"] for candidate in candidates if candidate["prefix"]})

    for prefix in explicit_prefixes:
        modes.append(("prefix", prefix))

    if any(not candidate["prefix"] and candidate["line_start"] for candidate in candidates):
        modes.append(("line_start", ""))

    if any(not candidate["prefix"] and not candidate["line_start"] for candidate in candidates):
        modes.append(("inline", ""))

    if any(not candidate["prefix"] for candidate in candidates):
        modes.append(("no_prefix_any", ""))

    return modes


def _candidate_matches_mode(candidate, mode):
    mode_name, mode_value = mode

    if mode_name == "prefix":
        return candidate["prefix"] == mode_value
    if mode_name == "line_start":
        return not candidate["prefix"] and candidate["line_start"]
    if mode_name == "inline":
        return not candidate["prefix"] and not candidate["line_start"]
    if mode_name == "no_prefix_any":
        return not candidate["prefix"]

    return False


def _build_best_chain(candidates):
    if not candidates:
        return []

    filtered_candidates = sorted(candidates, key=lambda candidate: candidate["start"])
    best_chain_by_index = {}

    for idx in range(len(filtered_candidates) - 1, -1, -1):
        current = filtered_candidates[idx]
        best_following_chain = []

        for next_idx in range(idx + 1, len(filtered_candidates)):
            next_candidate = filtered_candidates[next_idx]
            if next_candidate["number"] != current["number"] + 1:
                continue

            following_chain = best_chain_by_index[next_idx]
            candidate_chain = [current, *following_chain]
            best_candidate_chain = [current, *best_following_chain]

            if len(candidate_chain) > len(best_candidate_chain):
                best_following_chain = following_chain
                continue

            if len(candidate_chain) == len(best_candidate_chain):
                current_end = candidate_chain[-1]["start"]
                best_end = best_candidate_chain[-1]["start"]
                if current_end > best_end:
                    best_following_chain = following_chain

        best_chain_by_index[idx] = [current, *best_following_chain]

    return max(best_chain_by_index.values(), key=_score_chain, default=[])


def _score_chain(chain):
    if not chain:
        return float("-inf")

    first = chain[0]
    last = chain[-1]
    coverage = last["start"] - first["start"]

    score = (len(chain) * 500) + coverage
    if first["number"] == 1:
        score += 250
    if first["start"] <= 40:
        score += 100
    if first["prefix"]:
        score += 150
        if first["start"] <= 40 and len(chain) >= 2:
            score += 1500
    if first["line_start"]:
        score += 50

    return score


def split_numbered_points(value: str):
    """
    Split text into numbered items like:
    1.
    2)
    3)
    4-
    +5.
    Also handles text before the first numbered item and prefers
    the dominant top-level sequence when nested sub-points exist.
    """
    if not value:
        return []

    text = value.strip()
    candidates = _find_point_candidates(text)

    if not candidates:
        return [text]

    split_positions = []
    best_chain = []

    for mode in _candidate_modes(candidates):
        mode_candidates = [
            candidate
            for candidate in candidates
            if _candidate_matches_mode(candidate, mode)
        ]
        candidate_chain = _build_best_chain(mode_candidates)
        if _score_chain(candidate_chain) > _score_chain(best_chain):
            best_chain = candidate_chain

    if len(best_chain) >= 2:
        split_positions = [candidate["start"] for candidate in best_chain]
    elif candidates[0]["start"] == 0:
        split_positions = [candidates[0]["start"]]
    else:
        split_positions = [
            candidate["start"]
            for candidate in candidates
            if candidate["line_start"] or candidate["prefix"]
        ]

    if not split_positions:
        return [text]

    parts = []

    if split_positions[0] > 0:
        leading_text = text[:split_positions[0]].strip()
        if leading_text:
            parts.append(leading_text)

    for idx, start_pos in enumerate(split_positions):
        end_pos = split_positions[idx + 1] if idx + 1 < len(split_positions) else len(text)
        part = text[start_pos:end_pos].strip()
        if part:
            parts.append(part)

    return parts


def renumber_point_for_display(point_text: str) -> str:
    """
    Normalize leading numbering to '1)'
    """
    stripped = point_text.strip()

    def _replace(match: re.Match) -> str:
        number = int(match.group(1))
        return f"{number}) "

    return LEADING_POINT_MARKER_PATTERN.sub(_replace, stripped, count=1).strip()


def format_field_for_display(code: str, value: str) -> str:
    if not value:
        return ""

    base_code = get_base_field_code(code)

    value = remove_classification_lines(value)
    value = remove_dot_separator_lines(value)
    value = normalize_general_value(value)
    value = remove_leading_field_label(base_code, value)

    if base_code in POINT_STRUCTURED_CODES:
        points = split_numbered_points(value)
        if points:
            points = [renumber_point_for_display(p) for p in points]
            return "\n\n".join(points)

    return value.strip()


def field_value_to_points(code: str, value: str):
    """
    Return a list of numbered points for structured fields.
    For non-structured fields, returns [].
    """
    if get_base_field_code(code) not in POINT_STRUCTURED_CODES or not value:
        return []

    points = split_numbered_points(value)
    points = [renumber_point_for_display(p) for p in points if p.strip()]
    return points
