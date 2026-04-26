import pytest
from wp_migration.transport import (
    connect,
    TransportProtocol,
    TransportError,
    ConnectionError as TransportConnectionError,
)


FTP_CLASS = "wp_migration.transport.ftpretty"
SSH_CLASS = "wp_migration.transport.paramiko.SSHClient"


class TestConnect:
    def test_connect_ftp(self, mocker):
        mocker.patch(FTP_CLASS)
        conn = connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")
        assert conn is not None

    def test_connect_sftp(self, mocker):
        mock_ssh = mocker.patch(SSH_CLASS)
        mock_ssh.return_value.get_transport.return_value = None
        conn = connect(TransportProtocol.SFTP, "host.com", 22, "user", "pass")
        assert conn is not None
        mock_ssh.return_value.connect.assert_called_once()

    def test_connect_scp(self, mocker):
        mock_ssh = mocker.patch(SSH_CLASS)
        mock_ssh.return_value.get_transport.return_value = None
        conn = connect(TransportProtocol.SCP, "host.com", 22, "user", "pass")
        assert conn is not None
        mock_ssh.return_value.connect.assert_called_once()

    def test_connect_ftp_failure_raises(self, mocker):
        mocker.patch(FTP_CLASS, side_effect=Exception("Connection refused"))
        with pytest.raises(TransportConnectionError, match="refused"):
            connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")

    def test_connect_sftp_failure_raises(self, mocker):
        mock_ssh = mocker.patch(SSH_CLASS)
        mock_ssh.return_value.connect.side_effect = Exception("Timeout")
        with pytest.raises(TransportConnectionError, match="Timeout"):
            connect(TransportProtocol.SFTP, "host.com", 22, "user", "pass")

    def test_connect_with_key_path_sftp(self, mocker):
        mock_ssh = mocker.patch(SSH_CLASS)
        mock_ssh.return_value.get_transport.return_value = None
        connect(TransportProtocol.SFTP, "host.com", 22, "user", key_path="/path/to/key")
        call_kwargs = mock_ssh.return_value.connect.call_args[1]
        assert call_kwargs.get("key_filename") == "/path/to/key"

    def test_connect_scp_with_password(self, mocker):
        mock_ssh = mocker.patch(SSH_CLASS)
        mock_ssh.return_value.get_transport.return_value = None
        connect(TransportProtocol.SCP, "host.com", 22, "user", password="secret")
        call_kwargs = mock_ssh.return_value.connect.call_args[1]
        assert call_kwargs.get("password") == "secret"

    def test_invalid_protocol_raises(self, mocker):
        with pytest.raises(ValueError, match="protocol"):
            connect("unknown", "host.com", 22, "user")


class TestExecCommand:
    def test_ssh_exec_command_runs_and_returns_stdout(self, mocker):
        mock_ssh = mocker.patch(SSH_CLASS)
        mock_ssh.return_value.get_transport.return_value = None
        mock_stdout = mocker.Mock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.return_value = b"hello world\n"
        mock_ssh.return_value.exec_command.return_value = (None, mock_stdout, None)
        conn = connect(TransportProtocol.SFTP, "host.com", 22, "user", "pass")
        result = conn.exec_command("echo hello")
        assert result == "hello world\n"
        mock_ssh.return_value.exec_command.assert_called_once_with("echo hello", timeout=600)

    def test_ssh_exec_command_non_zero_exit_raises(self, mocker):
        mock_ssh = mocker.patch(SSH_CLASS)
        mock_ssh.return_value.get_transport.return_value = None
        mock_stderr = mocker.Mock()
        mock_stderr.read.return_value = b"command not found"
        mock_stdout = mocker.Mock()
        mock_stdout.channel.recv_exit_status.return_value = 127
        mock_ssh.return_value.exec_command.return_value = (None, mock_stdout, mock_stderr)
        conn = connect(TransportProtocol.SFTP, "host.com", 22, "user", "pass")
        with pytest.raises(TransportError, match="127"):
            conn.exec_command("invalid_cmd")

    def test_ftp_exec_command_raises_not_implemented(self, mocker):
        mocker.patch(FTP_CLASS)
        conn = connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")
        with pytest.raises(NotImplementedError):
            conn.exec_command("anything")

    def test_exec_command_custom_timeout(self, mocker):
        mock_ssh = mocker.patch(SSH_CLASS)
        mock_ssh.return_value.get_transport.return_value = None
        mock_stdout = mocker.Mock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.return_value = b"ok"
        mock_ssh.return_value.exec_command.return_value = (None, mock_stdout, None)
        conn = connect(TransportProtocol.SCP, "host.com", 22, "user", "pass")
        conn.exec_command("sleep 10", timeout=30)
        mock_ssh.return_value.exec_command.assert_called_once_with("sleep 10", timeout=30)


class TestFtpConnection:
    def test_download(self, mocker):
        mock_ftp = mocker.patch(FTP_CLASS).return_value
        conn = connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")
        conn.download("/remote/file.txt", "/local/file.txt")
        mock_ftp.get.assert_called_once_with("/remote/file.txt", "/local/file.txt")

    def test_upload(self, mocker):
        mock_ftp = mocker.patch(FTP_CLASS).return_value
        conn = connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")
        conn.upload("/local/file.txt", "/remote/file.txt")
        mock_ftp.put.assert_called_once_with("/local/file.txt", "/remote/file.txt")

    def test_list(self, mocker):
        mock_ftp = mocker.patch(FTP_CLASS).return_value
        mock_ftp.list.return_value = ["file1.txt", "dir1/"]
        conn = connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")
        result = conn.list("/remote/dir")
        assert result == ["file1.txt", "dir1/"]

    def test_delete(self, mocker):
        mock_ftp = mocker.patch(FTP_CLASS).return_value
        conn = connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")
        conn.delete("/remote/file.txt")
        mock_ftp.delete.assert_called_once_with("/remote/file.txt")

    def test_exists_true(self, mocker):
        mock_ftp = mocker.patch(FTP_CLASS).return_value
        mock_ftp.list.return_value = ["wp-config.php", "wp-content/"]
        conn = connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")
        assert conn.exists("/wp-config.php") is True

    def test_exists_false(self, mocker):
        mock_ftp = mocker.patch(FTP_CLASS).return_value
        mock_ftp.list.return_value = ["wp-content/"]
        conn = connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")
        assert conn.exists("/wp-config.php") is False


class TestSftpConnection:
    def test_download(self, mocker):
        mock_sftp = mocker.patch(SSH_CLASS).return_value.open_sftp.return_value
        conn = connect(TransportProtocol.SFTP, "host.com", 22, "user", "pass")
        conn.download("/remote/file.txt", "/tmp/local.txt")
        mock_sftp.get.assert_called_once()

    def test_upload(self, mocker):
        mock_sftp = mocker.patch(SSH_CLASS).return_value.open_sftp.return_value
        conn = connect(TransportProtocol.SFTP, "host.com", 22, "user", "pass")
        conn.upload("/local/file.txt", "/remote/file.txt")
        mock_sftp.put.assert_called_once()

    def test_list(self, mocker):
        mock_sftp = mocker.patch(SSH_CLASS).return_value.open_sftp.return_value
        mock_sftp.listdir.return_value = ["file1.txt", "dir1"]
        conn = connect(TransportProtocol.SFTP, "host.com", 22, "user", "pass")
        result = conn.list("/remote/dir")
        assert result == ["file1.txt", "dir1"]

    def test_exists_true(self, mocker):
        mock_sftp = mocker.patch(SSH_CLASS).return_value.open_sftp.return_value
        mock_sftp.stat.return_value = mocker.Mock()
        conn = connect(TransportProtocol.SFTP, "host.com", 22, "user", "pass")
        assert conn.exists("/wp-config.php") is True

    def test_exists_false(self, mocker):
        mock_sftp = mocker.patch(SSH_CLASS).return_value.open_sftp.return_value
        mock_sftp.stat.side_effect = FileNotFoundError
        conn = connect(TransportProtocol.SFTP, "host.com", 22, "user", "pass")
        assert conn.exists("/wp-config.php") is False


class TestScpConnection:
    def test_download(self, mocker):
        mock_sftp = mocker.patch(SSH_CLASS).return_value.open_sftp.return_value
        conn = connect(TransportProtocol.SCP, "host.com", 22, "user", "pass")
        conn.download("/remote/file.txt", "/tmp/local.txt")
        mock_sftp.get.assert_called_once()

    def test_upload(self, mocker):
        mock_sftp = mocker.patch(SSH_CLASS).return_value.open_sftp.return_value
        conn = connect(TransportProtocol.SCP, "host.com", 22, "user", "pass")
        conn.upload("/local/file.txt", "/remote/file.txt")
        mock_sftp.put.assert_called_once()

    def test_list(self, mocker):
        mock_sftp = mocker.patch(SSH_CLASS).return_value.open_sftp.return_value
        mock_sftp.listdir.return_value = ["wp-config.php"]
        conn = connect(TransportProtocol.SCP, "host.com", 22, "user", "pass")
        assert conn.list("/remote") == ["wp-config.php"]


class TestProgressCallback:
    def test_upload_with_progress_callback(self, mocker):
        callback = mocker.Mock()
        mocker.patch(FTP_CLASS)
        conn = connect(TransportProtocol.FTP, "host.com", 21, "user", "pass")
        conn.upload("/local/file.txt", "/remote/file.txt", progress=callback)
        callback.assert_called()
