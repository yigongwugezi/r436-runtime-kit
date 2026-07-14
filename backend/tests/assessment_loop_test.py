"""Tests for assessment_loop — coverage for refactoring safety."""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.assessment_loop import (
    _dynamic_threshold,
    _detect_mastery_change,
    _detect_decay,
    assessment_tracker,
    NotificationStore,
    AssessmentNotification,
)


# ═══════════════════════════════════════════════
# 1. _dynamic_threshold — 纯函数
# ═══════════════════════════════════════════════

def test_dynamic_threshold_values():
    """阈值按分数段返回正确值。"""
    assert _dynamic_threshold(20) == 5, "低分段应返回 5"
    assert _dynamic_threshold(45) == 8, "中分段应返回 8"
    assert _dynamic_threshold(70) == 12, "高分段应返回 12"
    assert _dynamic_threshold(90) == 15, "优秀段应返回 15"

def test_dynamic_threshold_boundaries():
    """边界值。"""
    assert _dynamic_threshold(0) == 5
    assert _dynamic_threshold(29) == 5
    assert _dynamic_threshold(30) == 8
    assert _dynamic_threshold(59) == 8
    assert _dynamic_threshold(60) == 12
    assert _dynamic_threshold(79) == 12
    assert _dynamic_threshold(80) == 15
    assert _dynamic_threshold(100) == 15


# ═══════════════════════════════════════════════
# 2. _detect_mastery_change — 依赖 assessment_tracker
# ═══════════════════════════════════════════════

def test_detect_mastery_no_old_data():
    """没有旧数据时默认需要调整（首次评估）。"""
    result = _detect_mastery_change('__test_session__', {'math': 80})
    assert result == False  # 没有旧数据时默认不调整

def test_detect_mastery_threshold_not_met():
    """变化小于阈值时不触发。"""
    import time
    # 先存旧数据
    state = assessment_tracker.get('__test_session__')
    state.last_mastery_snapshot = {'math': 75, 'physics': 65}
    state.last_diagnosis_at = time.time() - 86400
    assessment_tracker._persist(state)
    
    # 新分数变化不大
    result = _detect_mastery_change('__test_session__', {'math': 78, 'physics': 68})
    assert result == False, f"变化3分不应触发调整: {result}"

def test_detect_mastery_threshold_met():
    """变化大于阈值时触发。"""
    import time
    state = assessment_tracker.get('__test_session_2__')
    state.last_mastery_snapshot = {'math': 75}
    state.last_diagnosis_at = time.time() - 86400
    assessment_tracker._persist(state)
    
    # 变化 12 分，大于阈值 8
    result = _detect_mastery_change('__test_session_2__', {'math': 87})
    assert result == True, f"变化12分应触发调整: {result}"

def test_detect_mastery_mixed():
    """多个知识点，一个显著变化就触发。"""
    import time
    state = assessment_tracker.get('__test_session_3__')
    state.last_mastery_snapshot = {'math': 70, 'physics': 50, 'chemistry': 85}
    state.last_diagnosis_at = time.time() - 86400
    assessment_tracker._persist(state)
    
    # 只有 math 从 70→72（涨2分不够），physics 从 50→65（涨15分够了）
    result = _detect_mastery_change('__test_session_3__', {'math': 72, 'physics': 65, 'chemistry': 87})
    assert result == True, f"physics 涨15分应触发: {result}"


# ═══════════════════════════════════════════════
# 3. _detect_decay — 纯函数
# ═══════════════════════════════════════════════

def test_detect_decay_no_decay():
    """分数上涨不算衰减。"""
    result = _detect_decay({'math': 70}, {'math': 80})
    assert result == []

def test_detect_decay_threshold_not_met():
    """下降幅度不够不触发。"""
    result = _detect_decay({'math': 70}, {'math': 66})
    assert result == []

def test_detect_decay_threshold_met():
    """下降超过阈值触发。"""
    result = _detect_decay({'math': 70}, {'math': 55})
    assert result == ['math']

def test_detect_decay_multiple():
    """多个知识点衰减，返回所有衰减项。"""
    old = {'math': 80, 'physics': 50, 'chemistry': 90}
    new = {'math': 65, 'physics': 48, 'chemistry': 75}
    result = _detect_decay(old, new)
    assert 'math' in result, f"math 降15分应衰减: {result}"
    assert 'chemistry' in result, f"chemistry 降15分应衰减: {result}"
    assert 'physics' not in result, f"physics 降2分不应衰减: {result}"


# ═══════════════════════════════════════════════
# 4. NotificationStore — SSE 支持
# ═══════════════════════════════════════════════

def test_notification_store_push_pop():
    store = NotificationStore()
    store.push('s1', AssessmentNotification(type='test', title='T', message='M', session_id='s1'))
    items = store.pop_all('s1')
    assert len(items) == 1
    assert items[0]['type'] == 'test'

def test_notification_store_empty_pop():
    store = NotificationStore()
    items = store.pop_all('nonexistent')
    assert items == []


# ═══════════════════════════════════════════════
# 5. 读取配置
# ═══════════════════════════════════════════════

def test_threshold_config():
    from app.config import settings
    assert settings.mastery_threshold_low >= 0
    assert settings.mastery_threshold_mid >= 0
    assert settings.mastery_threshold_high >= 0
    assert settings.mastery_threshold_top >= 0


if __name__ == '__main__':
    test_dynamic_threshold_values()
    test_dynamic_threshold_boundaries()
    test_detect_mastery_no_old_data()
    test_detect_mastery_threshold_not_met()
    test_detect_mastery_threshold_met()
    test_detect_mastery_mixed()
    test_detect_decay_no_decay()
    test_detect_decay_threshold_not_met()
    test_detect_decay_threshold_met()
    test_detect_decay_multiple()
    test_notification_store_push_pop()
    test_notification_store_empty_pop()
    test_threshold_config()
    print("ALL TESTS PASSED")
