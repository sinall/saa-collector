from contextvars import ContextVar


_collect_execution_context = ContextVar('collect_execution_context', default={})


def set_collect_execution_context(**context):
    clean_context = {
        key: value
        for key, value in context.items()
        if value is not None
    }
    return _collect_execution_context.set(clean_context)


def reset_collect_execution_context(token):
    _collect_execution_context.reset(token)


def get_collect_execution_context():
    return dict(_collect_execution_context.get() or {})


def format_collect_log_context(**extra_context):
    context = get_collect_execution_context()
    context.update({
        key: value
        for key, value in extra_context.items()
        if value is not None
    })
    ordered_keys = ('task_id', 'plan_id', 'job_id', 'data_type', 'unit')
    parts = [
        '{}={}'.format(key, context[key])
        for key in ordered_keys
        if context.get(key) is not None
    ]
    if not parts:
        return ''
    return '[{}] '.format(' '.join(parts))
