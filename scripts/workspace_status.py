"""Board execution ownership, independent of lifecycle approval/test gates."""


def validate_execution(value):
    if not isinstance(value, dict) or value.get('status') not in ('active', 'blocked'):
        raise ValueError('execution.status must be active or blocked')
    if not isinstance(value.get('summary'), str) or not value['summary'].strip():
        raise ValueError('execution.summary must describe the current work or wait reason')
    if value['status'] == 'blocked' and (
        not isinstance(value.get('requiredAction'), str) or not value['requiredAction'].strip()
    ):
        raise ValueError('Blocked execution requires a concrete user requiredAction')
    if value['status'] == 'active' and value.get('requiredAction'):
        raise ValueError('Active execution must clear the previous user requiredAction')


def is_open(item):
    state = str(item.get('status', 'open')).lower()
    return state not in ('closed', 'done', 'complete', 'completed', 'deferred', 'superseded', 'baseline-confirmed') and not state.startswith('resolved')


def concerns(detail):
    """Keep issue evidence visible without guessing who must act on it."""
    result = []

    def add(kind, item, phase=''):
        if isinstance(item, dict):
            if not is_open(item):
                return
            title = next((item[k] for k in ('summary', 'question', 'title', 'actual', 'id') if item.get(k)), '未填写说明')
            identifier = str(item.get('id', ''))
        else:
            title, identifier = str(item), ''
        result.append({'kind': kind, 'phase': phase, 'id': identifier, 'summary': str(title)})

    for item in detail['task'].get('blockers', []):
        add('任务问题', item)
    for phase_id, phase in detail['phases'].items():
        for item in phase.get('scope', {}).get('blockingDecisions', []):
            add('待决事项', item, phase_id)
        for item in phase.get('issues', []):
            add('问题记录', item, phase_id)
        for item in phase.get('tests', []):
            if isinstance(item, dict) and str(item.get('status', '')).upper() in ('FAIL', 'FAILED'):
                add('失败测试记录', item, phase_id)
        if phase.get('branch', {}).get('syncStatus') == 'STALE_PARENT':
            add('父版本待同步', 'STALE_PARENT', phase_id)
    for item in detail.get('comments', {}).get('threads', []):
        if isinstance(item, dict) and item.get('severity') == 'blocker':
            add('评审问题', item)
    for name in detail.get('dirtyExports', []):
        add('文件待同步', '外部修改需要合并：' + name)
    return result


def execution_status(detail):
    task = detail['task']
    phase = detail['phases'].get(task.get('activePhase'), {})
    execution = phase.get('execution')
    issues = concerns(detail)
    if task.get('state') == 'DONE':
        status, reason, action, source = 'done', '已完成，等待你手动归档', '', 'done'
    elif execution:
        try:
            validate_execution(execution)
        except ValueError:
            status, reason, action, source = 'active', '执行状态记录不完整，待 Agent 更新', '', 'unrecorded'
        else:
            status = execution['status']
            reason = execution['summary'].strip()
            action = execution.get('requiredAction', '').strip()
            source = 'recorded'
    else:
        status, reason, action, source = 'active', '尚未登记执行状态，以任务下一步为准', '', 'unrecorded'
    return {
        'status': status, 'statusReason': reason, 'requiredAction': action,
        'statusSource': source,
        'executionUpdatedAt': execution.get('updatedAt', '') if isinstance(execution, dict) else '',
        'blockers': [{'summary': reason, 'requiredAction': action}] if status == 'blocked' else [],
        'concerns': issues,
    }
