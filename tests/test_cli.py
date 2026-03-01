"""Unit tests for CLI parameter handling in lokki.cli."""

import argparse
import sys
from unittest.mock import patch

import pytest

from lokki import flow, main, step


class TestGetFlowParams:
    """Tests for _get_flow_params function."""

    def test_no_params(self) -> None:
        from lokki.cli import _get_flow_params

        @flow
        def empty_flow():
            return step(lambda: None)()

        params = _get_flow_params(empty_flow)
        assert params == {}

    def test_single_param(self) -> None:
        from lokki.cli import _get_flow_params

        @flow
        def single_param_flow(start_date: str):
            return step(lambda x: x)(start_date)

        params = _get_flow_params(single_param_flow)
        assert "start_date" in params
        assert params["start_date"].annotation is str

    def test_multiple_params(self) -> None:
        from lokki.cli import _get_flow_params

        @flow
        def multi_param_flow(start_date: str, limit: int = 100):
            return step(lambda x: x)(start_date)

        params = _get_flow_params(multi_param_flow)
        assert "start_date" in params
        assert "limit" in params


class TestCoerceValue:
    """Tests for _coerce_value function."""

    def test_string(self) -> None:
        from lokki.cli import _coerce_value

        assert _coerce_value("hello", str) == "hello"

    def test_int(self) -> None:
        from lokki.cli import _coerce_value

        assert _coerce_value("42", int) == 42

    def test_int_invalid(self) -> None:
        from lokki.cli import _coerce_value

        with pytest.raises(ValueError, match="Invalid integer value"):
            _coerce_value("abc", int)

    def test_float(self) -> None:
        from lokki.cli import _coerce_value

        assert _coerce_value("3.14", float) == 3.14

    def test_float_invalid(self) -> None:
        from lokki.cli import _coerce_value

        with pytest.raises(ValueError, match="Invalid float value"):
            _coerce_value("abc", float)

    def test_bool_true(self) -> None:
        from lokki.cli import _coerce_value

        assert _coerce_value("true", bool) is True
        assert _coerce_value("1", bool) is True
        assert _coerce_value("yes", bool) is True

    def test_bool_false(self) -> None:
        from lokki.cli import _coerce_value

        assert _coerce_value("false", bool) is False
        assert _coerce_value("0", bool) is False
        assert _coerce_value("no", bool) is False

    def test_bool_invalid(self) -> None:
        from lokki.cli import _coerce_value

        with pytest.raises(ValueError, match="Invalid boolean value"):
            _coerce_value("maybe", bool)

    def test_list_str(self) -> None:
        from lokki.cli import _coerce_value

        assert _coerce_value("a,b,c", list[str]) == ["a", "b", "c"]

    def test_list_int(self) -> None:
        from lokki.cli import _coerce_value

        assert _coerce_value("1,2,3", list[int]) == [1, 2, 3]


class TestParseFlowParams:
    """Tests for _parse_flow_params function."""

    def test_no_params(self) -> None:
        from lokki.cli import _parse_flow_params

        @flow
        def empty_flow():
            return step(lambda: None)()

        args = argparse.Namespace()
        params = _parse_flow_params(empty_flow, args)
        assert params == {}

    def test_optional_params_use_defaults(self) -> None:
        from lokki.cli import _parse_flow_params

        @flow
        def optional_flow(limit: int = 100):
            return step(lambda x: x)(limit)

        args = argparse.Namespace()
        params = _parse_flow_params(optional_flow, args)
        assert params == {}

    def test_mandatory_params_required(self) -> None:
        from lokki.cli import _parse_flow_params

        @flow
        def mandatory_flow(start_date: str):
            return step(lambda x: x)(start_date)

        args = argparse.Namespace()
        with pytest.raises(argparse.ArgumentError, match="Missing required parameter"):
            _parse_flow_params(mandatory_flow, args)

    def test_provided_params_parsed(self) -> None:
        from lokki.cli import _parse_flow_params

        @flow
        def test_flow(start_date: str, limit: int = 100):
            return step(lambda x: x)(start_date)

        args = argparse.Namespace()
        args.start_date = "2024-01-15"
        args.limit = None

        params = _parse_flow_params(test_flow, args)
        assert params == {"start_date": "2024-01-15"}

    def test_type_coercion(self) -> None:
        from lokki.cli import _parse_flow_params

        @flow
        def typed_flow(count: int, flag: bool):
            return step(lambda x: x)(count)

        args = argparse.Namespace()
        args.count = "42"
        args.flag = "true"

        params = _parse_flow_params(typed_flow, args)
        assert params == {"count": 42, "flag": True}

    def test_invalid_type_raises(self) -> None:
        from lokki.cli import _parse_flow_params

        @flow
        def typed_flow(count: int):
            return step(lambda x: x)(count)

        args = argparse.Namespace()
        args.count = "not-an-int"

        with pytest.raises(argparse.ArgumentTypeError, match="Invalid value"):
            _parse_flow_params(typed_flow, args)


class TestMainCLI:
    """Integration tests for the main CLI function."""

    @pytest.fixture
    def simple_flow(self):
        @step
        def get_data() -> list[str]:
            return ["a", "b", "c"]

        @flow
        def simple_flow():
            return get_data()

        return simple_flow

    @pytest.fixture
    def param_flow(self):
        @step
        def process(start_date: str, limit: int = 100) -> list[str]:
            return [start_date] * limit

        @flow
        def param_flow(start_date: str, limit: int = 100):
            return process(start_date, limit)

        return param_flow

    def test_help_flag(self, simple_flow, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["test.py", "--help"]):
                main(simple_flow)
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "run" in captured.out
        assert "build" in captured.out
        assert "deploy" in captured.out

    def test_run_command_no_params(self, simple_flow):
        with patch.object(sys, "argv", ["test.py", "run"]):
            with patch("lokki.runtime.local.LocalRunner.run") as mock_run:
                mock_run.return_value = ["a", "b", "c"]
                main(simple_flow)
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                assert call_args[0][0].name == "simple-flow"
                assert call_args[0][1] == {}

    def test_run_command_with_params(self, param_flow):
        with patch.object(
            sys, "argv", ["test.py", "run", "--start-date", "2024-01-15"]
        ):
            with patch("lokki.runtime.local.LocalRunner.run") as mock_run:
                mock_run.return_value = ["2024-01-15"]
                main(param_flow)
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                assert call_args[0][1] == {"start_date": "2024-01-15"}

    def test_run_command_with_params_equals_syntax(self, param_flow):
        with patch.object(sys, "argv", ["test.py", "run", "--start-date=2024-01-15"]):
            with patch("lokki.runtime.local.LocalRunner.run") as mock_run:
                mock_run.return_value = ["2024-01-15"]
                main(param_flow)
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                assert call_args[0][1] == {"start_date": "2024-01-15"}

    def test_run_command_missing_required_param(self, param_flow):
        with patch.object(sys, "argv", ["test.py", "run", "--limit", "50"]):
            with pytest.raises(SystemExit) as exc_info:
                main(param_flow)
        assert exc_info.value.code == 2

    def test_run_command_invalid_type(self, param_flow):
        with patch.object(
            sys,
            "argv",
            ["test.py", "run", "--start-date", "2024-01-15", "--limit", "not-int"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(param_flow)
        assert exc_info.value.code == 1

    def test_build_command(self, simple_flow):
        with patch.object(sys, "argv", ["test.py", "build"]):
            with patch("lokki.config.load_config") as mock_config:
                from lokki.config import LokkiConfig

                mock_config.return_value = LokkiConfig(artifact_bucket="test-bucket")
                with patch("lokki.builder.builder.Builder.build") as mock_build:
                    main(simple_flow)
                    mock_build.assert_called_once()

    def test_deploy_command(self, simple_flow):
        with patch.object(sys, "argv", ["test.py", "deploy", "--confirm"]):
            with patch("lokki.config.load_config") as mock_config:
                from lokki.config import LambdaConfig, LokkiConfig

                mock_config.return_value = LokkiConfig(
                    artifact_bucket="test-bucket", lambda_cfg=LambdaConfig()
                )
                with patch("lokki.builder.builder.Builder.build"):
                    with patch("lokki.cli.deploy.Deployer.deploy"):
                        main(simple_flow)

    def test_destroy_command_stub(self, simple_flow):
        with patch.object(sys, "argv", ["test.py", "destroy", "--confirm"]):
            with patch("lokki.cli.destroy.destroy_stack") as mock_destroy:
                mock_destroy.return_value = None
                with patch("lokki.config.load_config") as mock_config:
                    from lokki.config import LambdaConfig, LokkiConfig

                    mock_config.return_value = LokkiConfig(
                        artifact_bucket="test-bucket", lambda_cfg=LambdaConfig()
                    )
                    main(simple_flow)
                mock_destroy.assert_called_once()

    def test_status_command_stub(self, simple_flow):
        with patch.object(sys, "argv", ["test.py", "status"]):
            with pytest.raises(SystemExit) as exc_info:
                main(simple_flow)
        assert exc_info.value.code == 2

    def test_logs_command_stub(self, simple_flow):
        with patch.object(sys, "argv", ["test.py", "logs"]):
            with patch("lokki.cli.logs.fetch_logs") as mock_logs:
                mock_logs.return_value = None
                with patch("lokki.config.load_config") as mock_config:
                    from lokki.config import LambdaConfig, LokkiConfig

                    mock_config.return_value = LokkiConfig(
                        artifact_bucket="test-bucket", lambda_cfg=LambdaConfig()
                    )
                    main(simple_flow)
                mock_logs.assert_called_once()

    def test_unknown_command(self, simple_flow):
        with patch.object(sys, "argv", ["test.py", "unknown"]):
            with pytest.raises(SystemExit) as exc_info:
                main(simple_flow)
        assert exc_info.value.code == 2

    def test_show_command(self, simple_flow):
        with patch.object(sys, "argv", ["test.py", "show"]):
            with patch("lokki.config.load_config") as mock_config:
                from lokki.config import LambdaConfig, LokkiConfig

                mock_config.return_value = LokkiConfig(
                    artifact_bucket="test-bucket", lambda_cfg=LambdaConfig()
                )
                with patch("lokki.cli.show.show_executions") as mock_show:
                    mock_show.return_value = [
                        {
                            "run_id": "test-run",
                            "status": "SUCCEEDED",
                            "start_time": "2024-01-15T10:00:00+00:00",
                            "duration": "1m 30s",
                        }
                    ]
                    main(simple_flow)
                    mock_show.assert_called_once()

    def test_logs_command(self, simple_flow):
        with patch.object(sys, "argv", ["test.py", "logs"]):
            with patch("lokki.config.load_config") as mock_config:
                from lokki.config import LambdaConfig, LokkiConfig

                mock_config.return_value = LokkiConfig(
                    artifact_bucket="test-bucket", lambda_cfg=LambdaConfig()
                )
                with patch("lokki.cli.logs.logs") as mock_logs:
                    mock_logs.return_value = None
                    main(simple_flow)
                    mock_logs.assert_called_once()

    def test_run_command_runner_error(self, simple_flow):
        """Test error handling when runner fails."""
        with patch.object(sys, "argv", ["test.py", "run"]):
            with patch("lokki.runtime.local.LocalRunner.run") as mock_run:
                mock_run.side_effect = RuntimeError("Runner failed")
                with pytest.raises(SystemExit) as exc_info:
                    main(simple_flow)
                assert exc_info.value.code == 1
