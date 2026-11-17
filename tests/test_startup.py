import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from stock_report import gui
from stock_report.cli import main


class StartupTests(unittest.TestCase):
    def run_widget(self, *, tray_available=True, connected=False, start_in_tray=True):
        with ExitStack() as stack:
            directory = stack.enter_context(tempfile.TemporaryDirectory())
            mocks = {name: stack.enter_context(patch.object(gui, name)) for name in
                     ('QApplication', 'Window', 'QLocalSocket', 'QLocalServer', 'QLockFile', 'icon')}
            mocks['QLocalSocket'].return_value.waitForConnected.return_value = connected
            mocks['QLockFile'].return_value.tryLock.return_value = True
            mocks['Window'].return_value.tray.isVisible.return_value = tray_available
            mocks['QApplication'].return_value.exec.return_value = 0
            result = gui.run(Path(directory) / 'test.sqlite3', compact=True, start_in_tray=start_in_tray)
            self.assertEqual(result, 0)
            return mocks

    def test_tray_start_stays_hidden_and_survives_window_close(self):
        mocks = self.run_widget()
        mocks['Window'].return_value.show.assert_not_called()
        mocks['Window'].return_value.toggle_compact.assert_called_once()
        mocks['QApplication'].return_value.setQuitOnLastWindowClosed.assert_called_once_with(False)

    def test_normal_launch_and_missing_tray_show_window(self):
        for options in ({'start_in_tray': False}, {'tray_available': False}):
            with self.subTest(options=options):
                mocks = self.run_widget(**options)
                mocks['Window'].return_value.show.assert_called_once()

    def test_existing_instance_receives_launch_intent(self):
        for start_in_tray, message in ((True, b'tray'), (False, b'show')):
            with self.subTest(start_in_tray=start_in_tray):
                mocks = self.run_widget(connected=True, start_in_tray=start_in_tray)
                mocks['QLocalSocket'].return_value.write.assert_called_once_with(message)
                mocks['Window'].assert_not_called()

    def test_existing_instance_opens_only_for_explicit_window_launch(self):
        for message in (b'tray', b'show'):
            with self.subTest(message=message):
                mocks = self.run_widget()
                server = mocks['QLocalServer'].return_value
                connection = server.nextPendingConnection.return_value
                connection.readAll.return_value = message
                accept = server.newConnection.connect.call_args.args[0]
                accept()
                window = mocks['Window'].return_value
                self.assertEqual(window.showNormal.called, message == b'show')
                connection.disconnectFromServer.assert_called_once()

    def test_cli_passes_tray_option(self):
        with patch.object(gui, 'run', return_value=0) as run:
            self.assertEqual(main(['widget', '--compact', '--tray']), 0)
            self.assertEqual(run.call_args.kwargs, {'start_in_tray': True})
