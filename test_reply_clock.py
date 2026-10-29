import unittest
from unittest.mock import Mock

import reply_clock as clock


class ClockTests(unittest.TestCase):
    def invoke(self, *, mode='watch', enabled=True, at=0, started=0, minutes=15,
               launch=None):
        self.at = at
        self.waits = []
        self.launch = launch or Mock()

        def sleep(seconds):
            self.waits.append(seconds)
            self.at += seconds

        return clock.continue_checks(
            started, enabled=enabled, mode=mode, minutes=minutes,
            clock=lambda: self.at, sleep=sleep, launch=self.launch,
            report=lambda *args, **kwargs: None,
        )

    def test_checks_continue_at_the_interval_without_cron(self):
        result = self.invoke(at=180)
        self.assertEqual(sum(self.waits), 720)
        self.assertLessEqual(max(self.waits), 30)
        self.launch.assert_called_once_with()
        self.assertEqual(result['next_mode'], 'watch')

    def test_activation_immediately_hands_over_to_a_fresh_worker(self):
        self.invoke(mode='start', at=180)
        self.assertEqual(self.waits, [])
        self.launch.assert_called_once_with()

    def test_slow_scan_does_not_add_another_full_interval(self):
        self.invoke(at=950)
        self.assertEqual(self.waits, [])
        self.launch.assert_called_once_with()

    def test_disabled_and_one_off_checks_never_start_a_worker(self):
        for mode, enabled in [('watch', False), ('run', True), ('scan', True), ('check', True)]:
            result = self.invoke(mode=mode, enabled=enabled)
            self.assertFalse(result['dispatched'])
            self.launch.assert_not_called()
            self.assertEqual(self.waits, [])

    def test_dispatch_failure_is_not_reported_as_success(self):
        launch = Mock(side_effect=RuntimeError('dispatch unavailable'))
        with self.assertRaises(RuntimeError):
            self.invoke(mode='start', launch=launch)
        launch.assert_called_once_with()

    def test_invalid_interval_stops_before_dispatch(self):
        for minutes in [0, 16]:
            with self.assertRaises(RuntimeError):
                self.invoke(minutes=minutes)
            self.launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
