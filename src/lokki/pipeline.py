"""Pipeline execution engine for Lokki library."""

import argparse
import inspect
import json
import os
from collections.abc import Callable
from typing import Any

from .data_store import DataStore, TempFileDataStore
from .decorators import StepTracker
from .models import StepArtifact, StepNode


class Pipeline:
    """Main pipeline class that manages DAG execution with datastore support."""

    def __init__(
        self,
        flow_func: Callable,
        flow_name: str,
        datastore: DataStore | None = None,
    ) -> None:
        self.flow_func = flow_func
        self.flow_name = flow_name
        self.datastore = datastore or TempFileDataStore()
        self.steps: dict[str, StepNode] = {}
        self.execution_order: list[str] = []
        self.flow_signature = inspect.signature(flow_func)
        self._build_dag()

    def _build_dag(self) -> None:
        """Build the DAG by analyzing the flow function."""
        step_tracker = StepTracker()

        mock_args: dict[str, Any] = {}
        for param_name, param in self.flow_signature.parameters.items():
            if param.annotation is str:
                mock_args[param_name] = f"mock_{param_name}"
            elif param.annotation is int:
                mock_args[param_name] = 0
            elif param.annotation is float:
                mock_args[param_name] = 0.0
            else:
                mock_args[param_name] = None

        with step_tracker:
            try:
                self.flow_func(**mock_args)
            except Exception:
                pass

        self.steps = step_tracker.steps
        self._calculate_execution_order()

    def _calculate_execution_order(self) -> None:
        """Calculate topological order for step execution."""
        visited: set = set()
        temp_visited: set = set()
        order: list[str] = []

        def visit(step_name: str) -> None:
            if step_name in temp_visited:
                raise ValueError(
                    f"Circular dependency detected involving step: {step_name}"
                )
            if step_name in visited:
                return

            temp_visited.add(step_name)
            step = self.steps[step_name]
            for dep in step.dependencies:
                if dep in self.steps:
                    visit(dep)
            temp_visited.remove(step_name)
            visited.add(step_name)
            order.append(step_name)

        for step_name in self.steps:
            if step_name not in visited:
                visit(step_name)

        self.execution_order = order

    def _parse_cli_args(self) -> dict[str, Any]:
        """Parse command line arguments based on flow function signature."""
        parser = argparse.ArgumentParser(
            description=f"Execute {self.flow_name} pipeline"
        )

        for param_name, param in self.flow_signature.parameters.items():
            if param.annotation is str:
                parser.add_argument(
                    f"--{param_name}",
                    type=str,
                    required=param.default == inspect.Parameter.empty,
                )
            elif param.annotation is int:
                parser.add_argument(
                    f"--{param_name}",
                    type=int,
                    required=param.default == inspect.Parameter.empty,
                )
            elif param.annotation is float:
                parser.add_argument(
                    f"--{param_name}",
                    type=float,
                    required=param.default == inspect.Parameter.empty,
                )
            else:
                parser.add_argument(
                    f"--{param_name}",
                    type=str,
                    required=param.default == inspect.Parameter.empty,
                )

        args = parser.parse_args()
        return vars(args)

    def run(self, use_cache: bool = True, **kwargs: Any) -> Any:
        """Execute the pipeline with given parameters and datastore support."""
        if not kwargs:
            kwargs = self._parse_cli_args()

        bound_args = self.flow_signature.bind(**kwargs)
        bound_args.apply_defaults()

        step_results: dict[str, Any] = {}
        step_artifacts: dict[str, StepArtifact] = {}

        for step_name in self.execution_order:
            step = self.steps[step_name]

            if use_cache:
                cache_key = f"{self.flow_name}_{step_name}"
                if self.datastore.exists(cache_key):
                    try:
                        cached_value = self.datastore.retrieve(cache_key)
                        print(f"Using cached result for step: {step_name}")
                        step_results[step_name] = cached_value
                        continue
                    except Exception as e:
                        msg = f"Warning: Failed to load cached result for {step_name}"
                        print(msg, e)

            step_kwargs: dict[str, Any] = {}
            step_signature = inspect.signature(step.function)

            for param_name in step_signature.parameters:
                if param_name in bound_args.arguments:
                    step_kwargs[param_name] = bound_args.arguments[param_name]
                else:
                    for dep_step_name in step.dependencies:
                        if dep_step_name in step_results:
                            dep_result = step_results[dep_step_name]
                            step_kwargs[param_name] = dep_result
                            break

            try:
                print(f"Executing step: {step_name}")
                result = step.function(**step_kwargs)

                cache_key = f"{self.flow_name}_{step_name}"
                artifact = self.datastore.store_step_result(
                    step_name,
                    result,
                    metadata={
                        "flow_name": self.flow_name,
                        "step_name": step_name,
                        "execution_order": len(
                            [s for s in self.execution_order if s == step_name]
                        ),
                    },
                )

                step_results[step_name] = result
                step_artifacts[step_name] = artifact

            except Exception as e:
                raise RuntimeError(f"Error executing step '{step_name}': {e}") from e

        if self.execution_order:
            last_step = self.execution_order[-1]
            final_result = step_results[last_step]
            return final_result
        else:
            return self.flow_func(**bound_args.arguments)

    def build(self, output: str | None = None, include_artifacts: bool = True) -> str:
        """Serialize the DAG to a JSON file with optional artifact information."""
        if output is None:
            os.makedirs("out", exist_ok=True)
            output = f"out/{self.flow_name}.json"

        steps_info: list[dict[str, Any]] = []
        dependencies: dict[str, list[str]] = {}
        artifacts_info: dict[str, dict[str, Any]] = {}

        for step_name, step in self.steps.items():
            step_info = {
                "name": step_name,
                "function_name": step.function.__name__,
                "module": step.function.__module__,
                "dependencies": step.dependencies,
                "outputs": step.outputs,
            }
            steps_info.append(step_info)
            dependencies[step_name] = step.dependencies

        if include_artifacts and hasattr(self.datastore, "artifacts"):
            for artifact_id, artifact in self.datastore.artifacts.items():
                artifacts_info[artifact_id] = {
                    "step_name": artifact.step_name,
                    "storage_key": artifact.storage_key,
                    "metadata": artifact.metadata,
                }

        parameters: dict[str, str] = {}
        for param_name, param in self.flow_signature.parameters.items():
            parameters[param_name] = (
                str(param.annotation)
                if param.annotation != inspect.Parameter.empty
                else "Any"
            )

        dag_data: dict[str, Any] = {
            "name": self.flow_name,
            "steps": steps_info,
            "dependencies": dependencies,
            "parameters": parameters,
            "datastore_type": type(self.datastore).__name__,
            "execution_order": self.execution_order,
        }

        if artifacts_info:
            dag_data["artifacts"] = artifacts_info

        with open(output, "w") as f:
            json.dump(dag_data, f, indent=2)

        return output

    def cleanup(self) -> None:
        """Clean up datastore resources."""
        self.datastore.cleanup()
