import re
from dataclasses import dataclass, field


@dataclass
class ExtractedProfileFacts:
    facts: dict[str, str] = field(default_factory=dict)
    supplemental: dict[str, list[str]] = field(default_factory=dict)


def zh(codepoints: str) -> str:
    return "".join(chr(int(item, 16)) for item in codepoints.split())


DA_YI = zh("5927 4e00")
DA_ER = zh("5927 4e8c")
DA_SAN = zh("5927 4e09")
DA_SI = zh("5927 56db")
YAN_YI = zh("7814 4e00")
YAN_ER = zh("7814 4e8c")
YAN_SAN = zh("7814 4e09")
STUDENT = zh("5b66 751f")
UNDERGRAD = zh("672c 79d1 751f")
POSTGRAD = zh("7814 7a76 751f")
MALE = zh("7537 751f")
FEMALE = zh("5973 751f")

SOFTWARE = zh("8f6f 4ef6 5de5 7a0b")
COMPUTER_SCIENCE = zh("8ba1 7b97 673a 79d1 5b66 4e0e 6280 672f")
COMPUTER = zh("8ba1 7b97 673a")
AI_MAJOR = zh("4eba 5de5 667a 80fd")
ELECTRONIC_INFO = zh("7535 5b50 4fe1 606f")
COMMUNICATION = zh("901a 4fe1 5de5 7a0b")
AUTOMATION = zh("81ea 52a8 5316")
DATA_SCIENCE = zh("6570 636e 79d1 5b66")
BIG_DATA = zh("5927 6570 636e")
INFO_SECURITY = zh("4fe1 606f 5b89 5168")
NETWORK_ENGINEERING = zh("7f51 7edc 5de5 7a0b")
IOT = zh("7269 8054 7f51")

DATA_STRUCTURE = zh("6570 636e 7ed3 6784")
MACHINE_LEARNING = zh("673a 5668 5b66 4e60")
DEEP_LEARNING = zh("6df1 5ea6 5b66 4e60")
NEURAL_NETWORK = zh("795e 7ecf 7f51 7edc")
AI_INTRO = zh("4eba 5de5 667a 80fd 5bfc 8bba")
NLP = zh("81ea 7136 8bed 8a00 5904 7406")
LINEAR_ALGEBRA = zh("7ebf 6027 4ee3 6570")
ADVANCED_MATH = zh("9ad8 7b49 6570 5b66")
COMPUTER_NETWORK = zh("8ba1 7b97 673a 7f51 7edc")
OS = zh("64cd 4f5c 7cfb 7edf")
DATABASE = zh("6570 636e 5e93")
COMPILER = zh("7f16 8bd1 539f 7406")
ALGORITHM = zh("7b97 6cd5")

GRADE_PATTERNS: tuple[tuple[str, str], ...] = (
    (DA_YI, DA_YI),
    (DA_ER, DA_ER),
    (DA_SAN, DA_SAN),
    (DA_SI, DA_SI),
    (YAN_YI, YAN_YI),
    (YAN_ER, YAN_ER),
    (YAN_SAN, YAN_SAN),
    (zh("4e00 5e74 7ea7"), DA_YI),
    (zh("4e8c 5e74 7ea7"), DA_ER),
    (zh("4e09 5e74 7ea7"), DA_SAN),
    (zh("56db 5e74 7ea7"), DA_SI),
)

MAJOR_ALIASES: tuple[tuple[str, str], ...] = (
    (SOFTWARE, SOFTWARE),
    (zh("8f6f 5de5"), SOFTWARE),
    (COMPUTER_SCIENCE, COMPUTER_SCIENCE),
    (zh("8ba1 79d1"), COMPUTER_SCIENCE),
    (COMPUTER, COMPUTER),
    (AI_MAJOR, AI_MAJOR),
    (ELECTRONIC_INFO, ELECTRONIC_INFO),
    (COMMUNICATION, COMMUNICATION),
    (AUTOMATION, AUTOMATION),
    (DATA_SCIENCE, DATA_SCIENCE),
    (BIG_DATA, BIG_DATA),
    (INFO_SECURITY, INFO_SECURITY),
    (NETWORK_ENGINEERING, NETWORK_ENGINEERING),
    (IOT, IOT),
)

COURSE_ALIASES: tuple[tuple[str, str], ...] = (
    (DATA_STRUCTURE, DATA_STRUCTURE),
    (MACHINE_LEARNING, MACHINE_LEARNING),
    (DEEP_LEARNING, DEEP_LEARNING),
    (NEURAL_NETWORK, NEURAL_NETWORK),
    (AI_INTRO, AI_INTRO),
    (AI_MAJOR, AI_INTRO),
    (NLP, NLP),
    ("NLP", NLP),
    ("PYTHON", "PYTHON"),
    ("Python", "Python"),
    ("python", "Python"),
    (LINEAR_ALGEBRA, LINEAR_ALGEBRA),
    (ADVANCED_MATH, ADVANCED_MATH),
    (COMPUTER_NETWORK, COMPUTER_NETWORK),
    (OS, OS),
    (DATABASE, DATABASE),
    (COMPILER, COMPILER),
    (ALGORITHM, ALGORITHM),
)

WEAK_WORDS = (
    zh("4e0d 4f1a"),  # cannot do
    zh("4e0d 61c2"),
    zh("6ca1 5b66 8fc7"),
    zh("8584 5f31"),
    zh("8f83 5f31"),
    zh("6bd4 8f83 5f31"),
    zh("4e0d 592a 4f1a"),
    zh("5361"),
    zh("56f0 96be"),
)
GOOD_WORDS = (
    zh("8fd8 53ef 4ee5"),
    zh("53ef 4ee5"),
    zh("4e0d 9519"),
    zh("8f83 597d"),
    zh("6bd4 8f83 597d"),
    zh("719f 6089"),
    zh("4f1a"),
    zh("5b66 8fc7"),
    zh("638c 63e1"),
)

NO_VIDEO = (zh("4e0d 8981 89c6 9891"), zh("4e0d 559c 6b22 89c6 9891"), zh("522b 7ed9 89c6 9891"))


def extract_profile_facts(message: str) -> ExtractedProfileFacts:
    """Extract learner-profile facts from one utterance with deterministic rules."""

    text = re.sub(r"\s+", " ", message.strip())
    result = ExtractedProfileFacts()
    if not text:
        return result

    _extract_background(text, result)
    _extract_course(text, result)
    _extract_learning_levels(text, result)
    _extract_goal(text, result)
    _extract_time_budget(text, result)
    _extract_preference(text, result)
    _extract_supplemental(text, result)
    return result


def _put_fact(result: ExtractedProfileFacts, key: str, value: str | None) -> None:
    cleaned = _clean(value)
    if cleaned:
        result.facts[key] = cleaned


def _add_supplemental(result: ExtractedProfileFacts, key: str, value: str | None) -> None:
    cleaned = _clean(value)
    if not cleaned:
        return
    values = result.supplemental.setdefault(key, [])
    if cleaned not in values:
        values.append(cleaned)


def _clean(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip(" ,.;:!?，。；：！？")
    return re.sub(r"\s+", "", value)


def _find_grade(text: str) -> str:
    return next((normalized for raw, normalized in GRADE_PATTERNS if raw in text), "")


def _find_major(text: str) -> str:
    return next((normalized for raw, normalized in MAJOR_ALIASES if raw in text), "")


def _find_major_background(text: str) -> str:
    return next((raw for raw, _ in MAJOR_ALIASES if raw in text), "")


def _find_courses(text: str) -> list[str]:
    courses: list[str] = []
    for raw, normalized in COURSE_ALIASES:
        if raw in text and normalized not in courses:
            courses.append(normalized)
    return courses


def _find_course_labels(text: str) -> list[str]:
    courses: list[str] = []
    for raw, _ in COURSE_ALIASES:
        if raw in text:
            label = "Python" if raw == "python" else raw
            if label not in courses:
                courses.append(label)
    return courses


def _extract_background(text: str, result: ExtractedProfileFacts) -> None:
    grade = _find_grade(text)
    major = _find_major_background(text)
    role = ""
    if POSTGRAD in text:
        role = POSTGRAD
    elif zh("672c 79d1") in text:
        role = UNDERGRAD
    elif STUDENT in text:
        role = STUDENT

    has_background_context = any(token in text for token in ("\u6211\u662f", "\u672c\u4eba\u662f", "\u4e13\u4e1a", "\u5b66\u751f", "\u5e74\u7ea7"))
    if grade or (major and (role or has_background_context)):
        _put_fact(result, "background", f"{major}{grade}{role}")
        return

    match = re.search(r"(?:\u6211\u662f|\u672c\u4eba\u662f|\u6211\u7684\u4e13\u4e1a\u662f)([^，。,.!?！？；;]{2,24})", text)
    if match:
        value = match.group(1)
        if value in {MALE, FEMALE, zh("7537"), zh("5973"), STUDENT, zh("5927 5b66 751f")}:
            _add_supplemental(result, "personal_background", value)
        else:
            _put_fact(result, "background", value)


def _extract_course(text: str, result: ExtractedProfileFacts) -> None:
    correction = re.search(
        r"(?:\u4e0d\u662f|\u4e0d\u8981\u5b66)[^，。,.!?！？；;]{1,20}(?:，|,)?(?:\u6211\u8981|\u6211\u60f3|\u6539\u6210|\u6362\u6210|\u5b66\u4e60)([^，。,.!?！？；;]{2,20})",
        text,
    )
    if correction:
        courses = _find_course_labels(correction.group(1))
        _put_fact(result, "target_course", courses[0] if courses else correction.group(1))
        return

    courses = _find_course_labels(text)
    if courses and any(
        word in text
        for word in (
            zh("60f3 5b66"),
            zh("6211 8981 5b66"),
            zh("590d 4e60"),
            zh("8003 8bd5"),
            zh("5165 95e8"),
            zh("89c4 5212"),
            zh("751f 6210"),
        )
    ):
        _put_fact(result, "target_course", courses[0])


def _extract_learning_levels(text: str, result: ExtractedProfileFacts) -> None:
    strengths: list[str] = []
    weaknesses: list[str] = []
    for course in _find_course_labels(text):
        window = _course_window(text, course)
        if any(word in window for word in WEAK_WORDS):
            weaknesses.append(f"{course}\uff1a{zh('4e0d 4f1a')}/{zh('4e0d 719f')}")
        elif any(word in window for word in GOOD_WORDS):
            strengths.append(f"{course}\uff1a{zh('8fd8 53ef 4ee5')}")

    if strengths:
        _put_fact(result, "knowledge_base", "\uff1b".join(strengths))
    if weaknesses:
        _put_fact(result, "weak_points", "\uff1b".join(weaknesses))

    weak_fragment = re.search(
        r"([^，。,.!?！？；;]{1,20})(?:\u6bd4\u8f83\u5f31|\u8f83\u5f31|\u8584\u5f31|\u4e0d\u592a\u4f1a|\u4e0d\u4f1a|\u4e0d\u61c2|\u5361\u4f4f|\u5f88\u96be)",
        text,
    )
    if weak_fragment and "weak_points" not in result.facts:
        _put_fact(result, "weak_points", f"{weak_fragment.group(1)}{zh('8f83 8584 5f31')}")


def _course_window(text: str, course: str) -> str:
    index = text.find(course)
    if index < 0:
        return text
    left = max(text.rfind(mark, 0, index) for mark in ("，", "。", ",", ".", "；", ";", "！", "？"))
    right_candidates = [text.find(mark, index + len(course)) for mark in ("，", "。", ",", ".", "；", ";", "！", "？")]
    right_candidates = [item for item in right_candidates if item >= 0]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1 : right]


def _extract_goal(text: str, result: ExtractedProfileFacts) -> None:
    goal_markers = (
        zh("8003 8bd5"),
        zh("901a 8fc7"),
        zh("9879 76ee"),
        zh("5165 95e8"),
        zh("67e5 6f0f 8865 7f3a"),
        zh("8bfe 7a0b 5b9e 9a8c"),
        zh("6bd5 4e1a"),
        zh("9762 8bd5"),
        zh("7ade 8d5b"),
    )
    if any(marker in text for marker in goal_markers):
        _put_fact(result, "learning_goal", text)


def _extract_time_budget(text: str, result: ExtractedProfileFacts) -> None:
    unit = r"(?:\u5c0f\u65f6|\u5206\u949f|\u5929|\u5468|\u4e2a\u6708)"
    match = re.search(rf"(?:\u6bcf\u5929)?\d+\s*{unit}(?:\u5b8c\u6210|\u5b66\u5b8c|\u5de6\u53f3|\u4ee5\u5185|\u4ee5\u4e0a)?", text)
    if not match:
        match = re.search(r"(?:\u4e00\u5468|\u4e24\u5468|\u4e09\u5468|\u4e00\u4e2a\u6708|\u534a\u4e2a\u6708|\u4e24\u5929|\u4e09\u5929|\u56db\u5341\u516b\u5c0f\u65f6)", text)
    if match:
        _put_fact(result, "time_budget", match.group(0))


def _extract_preference(text: str, result: ExtractedProfileFacts) -> None:
    formats: list[str] = []
    options = (
        (zh("6587 5b57 8bb2 89e3"), (zh("6587 5b57"), "markdown", "Markdown")),
        (zh("56fe 89e3"), (zh("56fe 89e3"), zh("753b 56fe"), zh("56fe"))),
        (zh("89c6 9891") + "/" + zh("52a8 753b"), (zh("89c6 9891"), zh("811a 672c"), zh("52a8 753b"))),
        (zh("4ee3 7801 5b9e 9a8c"), (zh("4ee3 7801"), zh("5b9e 64cd"), zh("5b9e 9a8c"))),
        (zh("7ec3 4e60 9898"), (zh("7ec3 4e60"), zh("9898"), zh("9898 5e93"))),
        ("PPT", ("ppt", "PPT")),
    )
    for label, words in options:
        if label == zh("89c6 9891") + "/" + zh("52a8 753b") and any(word in text for word in NO_VIDEO):
            continue
        if any(word in text for word in words):
            formats.append(label)
    if formats:
        _put_fact(result, "preference", "\u3001".join(dict.fromkeys(formats)))


def _extract_supplemental(text: str, result: ExtractedProfileFacts) -> None:
    for value in (MALE, FEMALE, zh("8fd0 52a8 5458")):
        if value in text:
            _add_supplemental(result, "personal_background", value)
