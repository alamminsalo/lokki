"""Unit tests for lokki runtime handler module."""

from unittest.mock import MagicMock, patch

from lokki.runtime.handler import make_handler


class TestMakeHandler:
    @patch("lokki.runtime.handler.load_config")
    @patch("lokki.runtime.handler.s3")
    def test_first_step_no_input(
        self, mock_s3: MagicMock, mock_config: MagicMock
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.artifact_bucket = "test-bucket"
        mock_cfg.flow_name = "test-flow"
        mock_config.return_value = mock_cfg

        def my_step(name: str = "world") -> str:
            return f"hello {name}"

        handler = make_handler(my_step)
        result = handler({"run_id": "test-run", "name": "test"}, MagicMock())

        assert result["run_id"] == "test-run"
        assert "result_url" in result

    @patch("lokki.runtime.handler.load_config")
    @patch("lokki.runtime.handler.s3")
    def test_single_input_via_result_url(
        self, mock_s3: MagicMock, mock_config: MagicMock
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.artifact_bucket = "test-bucket"
        mock_cfg.flow_name = "test-flow"
        mock_config.return_value = mock_cfg

        mock_s3.read.return_value = {"key": "value"}

        def process(data: dict) -> str:
            return data["key"]

        handler = make_handler(process)
        result = handler(
            {"run_id": "test-run", "result_url": "s3://bucket/key"}, MagicMock()
        )

        assert result["run_id"] == "test-run"
        assert "result_url" in result
        mock_s3.read.assert_called_once_with("s3://bucket/key")

    @patch("lokki.runtime.handler.load_config")
    @patch("lokki.runtime.handler.s3")
    def test_list_input_via_result_urls(
        self, mock_s3: MagicMock, mock_config: MagicMock
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.artifact_bucket = "test-bucket"
        mock_cfg.flow_name = "test-flow"
        mock_config.return_value = mock_cfg

        mock_s3.read.side_effect = ["a", "b", "c"]

        def collect(items: list[str]) -> str:
            return ",".join(items)

        handler = make_handler(collect)
        result = handler(
            {"run_id": "test-run", "result_urls": ["s3://b/1", "s3://b/2", "s3://b/3"]},
            MagicMock(),
        )

        assert result["run_id"] == "test-run"
        assert "result_url" in result
        assert mock_s3.read.call_count == 3

    @patch("lokki.runtime.handler.load_config")
    @patch("lokki.runtime.handler.s3")
    def test_map_source_writes_manifest(
        self, mock_s3: MagicMock, mock_config: MagicMock
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.artifact_bucket = "test-bucket"
        mock_cfg.flow_name = "test-flow"
        mock_config.return_value = mock_cfg

        mock_s3.write.side_effect = [
            "s3://test-bucket/lokki/test-flow/run1/get_items/0/output.pkl.gz",
            "s3://test-bucket/lokki/test-flow/run1/get_items/1/output.pkl.gz",
            "s3://test-bucket/lokki/test-flow/run1/get_items/2/output.pkl.gz",
            "s3://test-bucket/lokki/test-flow/run1/get_items/output.pkl.gz",
        ]

        def get_items() -> list[str]:
            return ["a", "b", "c"]

        handler = make_handler(get_items)
        result = handler({"run_id": "run1"}, MagicMock())

        assert "map_manifest_key" in result
        assert result["run_id"] == "run1"
        assert mock_s3.write.call_count == 4
        mock_s3.write_manifest.assert_called_once()
