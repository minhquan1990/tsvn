import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "levagent", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_demo_runs_offline(self) -> None:
        result = run("demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("backtest giả lập", result.stdout)
        self.assertIn("Kết quả quá khứ không phải lợi nhuận tương lai.", result.stdout)
        self.assertIn("không phải lời khuyên đầu tư", result.stdout)
        self.assertIn("xu hướng giả lập rất mượt", result.stdout)

    def test_bearish_headline_does_not_open_a_long(self) -> None:
        result = run("decide", "--synthetic", "--headline", "Bitcoin bị hack, nhà đầu tư phá sản")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("VÀO LỆNH MUA", result.stdout)

    def test_illegal_leverage_is_rejected(self) -> None:
        result = run("demo", "--leverage", "25")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("đòn bẩy", result.stderr)

    def test_paper_run_persists_without_sending_an_order(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper.json"
            result = run("run", "--synthetic", "--state", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("GIẢ LẬP", result.stdout)
            self.assertTrue(path.exists())
            status = run("status", "--symbol", "BTCUSDT", "--state", str(path))
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("sổ giả lập", status.stdout)


if __name__ == "__main__":
    unittest.main()
