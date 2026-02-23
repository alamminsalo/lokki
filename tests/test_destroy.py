"""Unit tests for destroy command."""

from unittest.mock import MagicMock, patch

import pytest

from lokki.destroy import DestroyError, destroy_stack


class TestDestroyStack:
    """Tests for destroy_stack function."""

    @patch("lokki.destroy.get_cf_client")
    def test_destroy_stack_success(self, mock_boto_client) -> None:
        mock_cf = MagicMock()
        mock_boto_client.return_value = mock_cf
        mock_cf.describe_stacks.return_value = {"Stacks": [{"StackName": "test-stack"}]}

        destroy_stack(stack_name="test-stack", region="us-east-1", confirm=True)

        mock_cf.delete_stack.assert_called_once_with(StackName="test-stack")
        mock_cf.get_waiter.assert_called_once_with("stack_delete_complete")

    @patch("lokki.destroy.get_cf_client")
    def test_destroy_stack_not_found(self, mock_boto_client) -> None:
        from botocore.exceptions import ClientError

        mock_cf = MagicMock()
        mock_boto_client.return_value = mock_cf
        mock_cf.describe_stacks.side_effect = ClientError(
            {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}},
            "DescribeStacks",
        )

        with pytest.raises(DestroyError, match="does not exist"):
            destroy_stack(stack_name="nonexistent-stack", confirm=True)

    @patch("lokki.destroy.get_cf_client")
    def test_destroy_stack_delete_failure(self, mock_boto_client) -> None:
        from botocore.exceptions import ClientError

        mock_cf = MagicMock()
        mock_boto_client.return_value = mock_cf
        mock_cf.describe_stacks.return_value = {"Stacks": [{"StackName": "test-stack"}]}
        mock_cf.delete_stack.side_effect = ClientError(
            {"Error": {"Code": "ValidationError"}}, "DeleteStack"
        )

        with pytest.raises(DestroyError, match="Failed to delete"):
            destroy_stack(stack_name="test-stack", confirm=True)

    @patch("lokki.destroy.get_cf_client")
    def test_destroy_stack_waiter_failure(self, mock_boto_client) -> None:
        from botocore.exceptions import ClientError

        mock_cf = MagicMock()
        mock_boto_client.return_value = mock_cf
        mock_cf.describe_stacks.return_value = {"Stacks": [{"StackName": "test-stack"}]}
        mock_cf.get_waiter.return_value.wait.side_effect = ClientError(
            {"Error": {"Code": "WaiterFailure"}}, "Waiter"
        )

        with pytest.raises(DestroyError, match="failed or timed out"):
            destroy_stack(stack_name="test-stack", confirm=True)


class TestDestroyConfirmation:
    """Tests for destroy confirmation prompt."""

    @patch("lokki.destroy.input")
    @patch("lokki.destroy.get_cf_client")
    def test_user_aborts(self, mock_boto_client, mock_input) -> None:
        mock_input.return_value = "n"

        with pytest.raises(SystemExit) as exc_info:
            destroy_stack(stack_name="test-stack", confirm=False)

        assert exc_info.value.code == 0
        mock_input.assert_called_once()

    @patch("lokki.destroy.input")
    @patch("lokki.destroy.get_cf_client")
    def test_user_confirms_yes(self, mock_boto_client, mock_input) -> None:
        mock_input.return_value = "y"
        mock_cf = MagicMock()
        mock_boto_client.return_value = mock_cf
        mock_cf.describe_stacks.return_value = {"Stacks": [{"StackName": "test-stack"}]}

        destroy_stack(stack_name="test-stack", confirm=False)

        mock_cf.delete_stack.assert_called_once()

    @patch("lokki.destroy.input")
    @patch("lokki.destroy.get_cf_client")
    def test_user_confirms_yes_uppercase(self, mock_boto_client, mock_input) -> None:
        mock_input.return_value = "YES"
        mock_cf = MagicMock()
        mock_boto_client.return_value = mock_cf
        mock_cf.describe_stacks.return_value = {"Stacks": [{"StackName": "test-stack"}]}

        destroy_stack(stack_name="test-stack", confirm=False)

        mock_cf.delete_stack.assert_called_once()
