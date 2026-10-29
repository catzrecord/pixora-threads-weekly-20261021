"""Continue the existing serialized reply worker without depending on cron delivery."""
import argparse
import json
import os
import subprocess
import time

import autoresponder as replies

REPO = 'catzrecord/pixora-threads-weekly-20261021'


def dispatch():
    subprocess.run(
        ['gh', 'workflow', 'run', 'auto-replies.yml', '--repo', REPO,
         '--ref', 'main', '-f', 'mode=watch'],
        check=True, capture_output=True,
    )


def continue_checks(started_at, *, enabled, mode, minutes, clock=time.time,
                    sleep=time.sleep, launch=dispatch, report=print):
    if not enabled or mode not in ('start', 'watch'):
        return {'state': 'reply_clock_inactive', 'dispatched': False}
    if not 1 <= minutes <= 15:
        raise RuntimeError('Reply polling interval must be between 1 and 15 minutes')
    deadline = clock() if mode == 'start' else started_at + minutes * 60
    report(json.dumps({'state': 'reply_clock_waiting',
                       'seconds_to_next_check': max(0, round(deadline-clock())),
                       'published_by_clock': 0}), flush=True)
    while clock() < deadline:
        sleep(min(30, deadline-clock()))
    launch()
    return {'state': 'reply_worker_dispatched', 'next_mode': 'watch',
            'dispatched': True, 'published_by_clock': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--started-at', type=float, required=True)
    args = parser.parse_args()
    try:
        result = continue_checks(
            args.started_at, enabled=os.environ.get('AUTO_REPLY_ENABLED') == 'true',
            mode=os.environ.get('MODE', ''), minutes=replies.config()['poll_minutes'],
        )
        print(json.dumps(result), flush=True)
    except Exception:
        print(json.dumps({'state': 'reply_clock_failed', 'dispatched': False,
                          'published_by_clock': 0}), flush=True)
        raise SystemExit(1)
