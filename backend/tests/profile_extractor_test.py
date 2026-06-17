import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.conversation_state import conversation_store  # noqa: E402
from app.services.profile_extractor import (  # noqa: E402
    DA_ER,
    DA_YI,
    DATA_STRUCTURE,
    LINEAR_ALGEBRA,
    MACHINE_LEARNING,
    NEURAL_NETWORK,
    SOFTWARE,
    STUDENT,
    extract_profile_facts,
    zh,
)


def test_short_identity_fragment_extracts_background() -> None:
    extracted = extract_profile_facts(f"{DA_YI} {STUDENT} {zh('8ba1 7b97 673a')}")
    assert extracted.facts["background"] == f"{zh('8ba1 7b97 673a')}{DA_YI}{STUDENT}"


def test_rich_profile_sentence_extracts_multiple_slots() -> None:
    message = (
        f"{zh('6211 662f')}{SOFTWARE}{DA_ER}{STUDENT}"
        f"{zh('ff0c 4e0d 4f1a')}Python"
        f"{zh('ff0c')}{DATA_STRUCTURE}{zh('8fd8 53ef 4ee5')}"
        f"{zh('ff0c')}{LINEAR_ALGEBRA}{zh('8fd8 53ef 4ee5')}"
        f"{zh('ff0c 4e0d 4f1a')}{MACHINE_LEARNING}"
    )
    extracted = extract_profile_facts(message)
    assert extracted.facts["background"] == f"{SOFTWARE}{DA_ER}{STUDENT}"
    assert f"{DATA_STRUCTURE}{zh('ff1a 8fd8 53ef 4ee5')}" in extracted.facts["knowledge_base"]
    assert f"{LINEAR_ALGEBRA}{zh('ff1a 8fd8 53ef 4ee5')}" in extracted.facts["knowledge_base"]
    assert "Python" in extracted.facts["weak_points"]
    assert MACHINE_LEARNING in extracted.facts["weak_points"]


def test_course_correction_overwrites_target_course_in_session() -> None:
    sid = "profile_extractor_course_correction"
    conversation_store.reset(sid)
    state = conversation_store.append_message(sid, "user", f"{zh('6211 60f3 5b66')}{MACHINE_LEARNING}")
    assert state.facts["target_course"] == MACHINE_LEARNING

    state = conversation_store.append_message(
        sid,
        "user",
        f"{zh('4e0d 662f')}{MACHINE_LEARNING}{zh('ff0c 6211 8981 5b66')}{DATA_STRUCTURE}",
    )
    assert state.facts["target_course"] == DATA_STRUCTURE


def test_preference_keeps_no_video_request() -> None:
    message = zh("4e0d 8981 89c6 9891 ff0c 591a 7ed9 6211 9898 548c 4ee3 7801 5b9e 9a8c")
    extracted = extract_profile_facts(message)
    assert zh("7ec3 4e60 9898") in extracted.facts["preference"]
    assert zh("4ee3 7801 5b9e 9a8c") in extracted.facts["preference"]
    assert zh("89c6 9891") not in extracted.facts["preference"]


def test_time_and_goal_are_separate_slots() -> None:
    message = f"{zh('6211 60f3 0034 0038 5c0f 65f6 5b8c 6210')}{NEURAL_NETWORK}{zh('5165 95e8')}"
    extracted = extract_profile_facts(message)
    assert extracted.facts["time_budget"] == zh("0034 0038 5c0f 65f6 5b8c 6210")
    assert extracted.facts["target_course"] == NEURAL_NETWORK
    assert zh("5165 95e8") in extracted.facts["learning_goal"]


def test_gender_is_supplemental_not_core_background() -> None:
    extracted = extract_profile_facts(zh("6211 662f 7537 751f"))
    assert "background" not in extracted.facts
    assert zh("7537 751f") in extracted.supplemental["personal_background"]


if __name__ == "__main__":
    tests = [
        test_short_identity_fragment_extracts_background,
        test_rich_profile_sentence_extracts_multiple_slots,
        test_course_correction_overwrites_target_course_in_session,
        test_preference_keeps_no_video_request,
        test_time_and_goal_are_separate_slots,
        test_gender_is_supplemental_not_core_background,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
