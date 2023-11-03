#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#

"""The actions package is made to declare reusable pipeline components."""

from __future__ import annotations
from dataclasses import dataclass, field
from pipelines import main_logger

from typing import TYPE_CHECKING, Callable, Dict, List, Tuple, Union

import asyncer
from pipelines.models.contexts import PipelineContext
from pipelines.models.steps import Step, StepStatus

if TYPE_CHECKING:
    from pipelines.models.steps import StepResult

@dataclass
class Runnable:
    id: str
    step: Step
    # Dict or a function that takes a list of step results and returns a dict
    args: Union[Dict, Callable[[Dict[str, StepResult]], Dict]] = field(default_factory=dict)

def evaluate_run_args(args: Union[Dict, Callable[[Dict[str, StepResult]], Dict]], results: Dict[str, StepResult]) -> Dict:
    if callable(args):
        return args(results)
    return args

def _get_step_id_str(context: PipelineContext, step: Runnable) -> str:
    will_be_skipped = step.id in context.skip_steps
    return f"{step.id} (skipped)" if will_be_skipped else step.id

def pretty_log_steps_tree(context: PipelineContext, steps: List[Runnable | List[Runnable]]):
    """
    Outout a pretty log of the steps tree based on the runnable

    e.g.
    Steps to run:
    - metadata_validation
    - [version_follow_check, version_increment_check]
    - [run_all_tests, run_qa_checks]
    - test_steps
    """
    main_logger.info("Steps to Run:")
    for step in steps:
        if isinstance(step, Runnable):
            main_logger.info(f"- {_get_step_id_str(context, step)}")
        elif isinstance(step, list):
            ids = [_get_step_id_str(context, s) for s in step]
            ids_str = ", ".join(ids)
            main_logger.info(f"- [{ids_str}]")
        else:
            raise Exception(f"Unexpected step type: {type(step)}")


async def new_run_steps(
    context: PipelineContext,
    runnables: List[Runnable | List[Runnable]],
    results: Dict[str, StepResult] = {},
    fail_fast: bool = True,
) -> Dict[str, StepResult]:
    """Run multiple steps sequentially, or in parallel if steps are wrapped into a sublist.

    Args:
        runnables (List[Runnable]): List of steps to run.
        results (Dict[str, StepResult], optional): Dictionary of step results, used for recursion.

    Returns:
        Dict[str, StepResult]: Dictionary of step results.
    """
    if runnables and results == {}:
        pretty_log_steps_tree(context, runnables)

    # If there are no steps to run, return the results
    if not runnables:
        return results

    # If any of the previous steps failed, skip the remaining steps
    if fail_fast and any(result.status is StepStatus.FAILURE for result in results.values()):
        skipped_results = {}
        for runnable_step in runnables:
            if isinstance(runnable_step, Runnable):
                skipped_results[runnable_step.id] = runnable_step.step.skip()
            elif isinstance(runnable_step, list):
                for step in runnable_step:
                    skipped_results[step.id] = step.step.skip()
            else:
                raise Exception(f"Unexpected step type: {type(runnable_step)}")

        return {**results, **skipped_results}

    # Pop the next step to run
    steps_to_run, remaining_steps = runnables[0], runnables[1:]

    # wrap the step in a list if it is not already (allows for parallel steps)
    if not isinstance(steps_to_run, list):
        steps_to_run = [steps_to_run]

    async with asyncer.create_task_group() as task_group:
        tasks = []
        for step_to_run in steps_to_run:
            # skip step if its id is in the skip list
            if step_to_run.id in context.skip_steps:
                main_logger.info(f"Skipping step {step_to_run.id}")
                tasks.append(task_group.soonify(step_to_run.step.async_skip)("Skipped by user"))
            else:
                step_args = evaluate_run_args(step_to_run.args, results)
                tasks.append(task_group.soonify(step_to_run.step.run)(**step_args))

    new_results = {steps_to_run[i].id: task.value for i, task in enumerate(tasks)}

    return await new_run_steps(context, remaining_steps, {**results, **new_results}, fail_fast)



async def run_steps(
    steps_and_run_args: List[Union[Step, Tuple[Step, Tuple]] | List[Union[Step, Tuple[Step, Tuple]]]], results: List[StepResult] = []
) -> List[StepResult]:
    """Run multiple steps sequentially, or in parallel if steps are wrapped into a sublist.

    Args:
        steps_and_run_args (List[Union[Step, Tuple[Step, Tuple]] | List[Union[Step, Tuple[Step, Tuple]]]]): List of steps to run, if steps are wrapped in a sublist they will be executed in parallel. run function arguments can be passed as a tuple along the Step instance.
        results (List[StepResult], optional): List of step results, used for recursion.

    Returns:
        List[StepResult]: List of step results.
    """
    # If there are no steps to run, return the results
    if not steps_and_run_args:
        return results

    # If any of the previous steps failed, skip the remaining steps
    if any(result.status is StepStatus.FAILURE for result in results):
        skipped_results = []
        for step_and_run_args in steps_and_run_args:
            if isinstance(step_and_run_args, Tuple):
                skipped_results.append(step_and_run_args[0].skip())
            else:
                skipped_results.append(step_and_run_args.skip())
        return results + skipped_results

    # Pop the next step to run
    steps_to_run, remaining_steps = steps_and_run_args[0], steps_and_run_args[1:]

    # wrap the step in a list if it is not already (allows for parallel steps)
    if not isinstance(steps_to_run, list):
        steps_to_run = [steps_to_run]

    async with asyncer.create_task_group() as task_group:
        tasks = []
        for step in steps_to_run:
            if isinstance(step, Step):
                tasks.append(task_group.soonify(step.run)())
            elif isinstance(step, Tuple) and isinstance(step[0], Step) and isinstance(step[1], Tuple):
                step, run_args = step
                tasks.append(task_group.soonify(step.run)(*run_args))

    new_results = [task.value for task in tasks]

    return await run_steps(remaining_steps, results + new_results)
