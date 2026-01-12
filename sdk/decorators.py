"""Decorators and helpers for ergonomic X-Ray SDK instrumentation.

This module provides decorators and helper functions for declarative
pipeline instrumentation without manual step management.

Example:
    from sdk import step, attach_reasoning, current_run

    @step(step_type="filter")
    def filter_candidates(candidates):
        filtered = [c for c in candidates if c["score"] > 0.5]
        attach_reasoning({"threshold": 0.5, "removed": len(candidates) - len(filtered)})
        return filtered

    with client.start_run("pipeline") as run:
        result = filter_candidates(candidates)  # Automatically instrumented
"""

from __future__ import annotations

import inspect
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from shared.types import StepType

from .client import current_run, current_step

if TYPE_CHECKING:
    from ._internal.step import Step

# Type variables for generic decorator typing
F = TypeVar("F", bound=Callable[..., Any])


def step(
    name: str | None = None,
    step_type: StepType | str = StepType.other,
) -> Callable[[F], F]:
    """Decorator to automatically instrument a function as a step.

    When a function decorated with @step is called within an active Run context,
    it automatically creates a Step, executes the function, and ends the Step
    with the result (or error if an exception is raised).

    If no Run is active, the function executes normally without instrumentation.

    Args:
        name: Step name (defaults to function.__name__)
        step_type: Type of step (filter, rank, llm, retrieval, transform, other)

    Returns:
        Decorated function that auto-instruments when Run is active.

    Example:
        @step(step_type="filter")
        def filter_candidates(candidates):
            return [c for c in candidates if c["score"] > 0.5]

        @step(name="custom_name", step_type="llm")
        async def call_llm(prompt):
            return await llm.complete(prompt)
    """

    def decorator(func: F) -> F:
        step_name = name or func.__name__

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                run = current_run()
                if run is None:
                    # No active run - execute without instrumentation
                    return await func(*args, **kwargs)

                # Capture all args and kwargs as input data
                input_data = {"args": args, "kwargs": kwargs} if args or kwargs else None
                step_obj = run.start_step(step_name, step_type, input_data)

                try:
                    result = await func(*args, **kwargs)
                    step_obj.end(result)
                    return result
                except BaseException as e:
                    step_obj.end_with_error(e)
                    raise

            # Mark as step-decorated to prevent double instrumentation
            async_wrapper._xray_step_decorated = True  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]
        else:

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                run = current_run()
                if run is None:
                    # No active run - execute without instrumentation
                    return func(*args, **kwargs)

                # Capture all args and kwargs as input data
                input_data = {"args": args, "kwargs": kwargs} if args or kwargs else None
                step_obj = run.start_step(step_name, step_type, input_data)

                try:
                    result = func(*args, **kwargs)
                    step_obj.end(result)
                    return result
                except BaseException as e:
                    step_obj.end_with_error(e)
                    raise

            # Mark as step-decorated to prevent double instrumentation
            sync_wrapper._xray_step_decorated = True  # type: ignore[attr-defined]
            return sync_wrapper  # type: ignore[return-value]

    return decorator


def instrument_class(
    cls: type | None = None,
    *,
    step_type: StepType | str = StepType.other,
    exclude: tuple[str, ...] = (),
) -> type | Callable[[type], type]:
    """Class decorator to instrument all public methods as steps.

    Applies the @step decorator to all public methods (methods not starting
    with underscore) of a class. Private methods and dunder methods are skipped.

    Can be used with or without parentheses:
        @instrument_class
        class MyClass: ...

        @instrument_class(step_type="filter")
        class MyClass: ...

    Args:
        cls: The class to instrument (auto-passed when used without parens)
        step_type: Default step type for all methods
        exclude: Method names to exclude from instrumentation

    Returns:
        Decorated class with instrumented public methods.

    Example:
        @instrument_class(step_type="filter", exclude=("helper_method",))
        class FilterPipeline:
            def filter_by_price(self, items):
                return [i for i in items if i["price"] < 100]

            def filter_by_rating(self, items):
                return [i for i in items if i["rating"] > 4.0]

            def helper_method(self, x):  # Not instrumented
                return x * 2
    """

    def decorate(cls: type) -> type:
        for attr_name in dir(cls):
            # Skip private/dunder methods
            if attr_name.startswith("_"):
                continue
            # Skip excluded methods
            if attr_name in exclude:
                continue

            # Get the raw attribute from class __dict__ to check for descriptors
            # This preserves staticmethod/classmethod detection
            raw_attr = None
            for klass in cls.__mro__:
                if attr_name in klass.__dict__:
                    raw_attr = klass.__dict__[attr_name]
                    break

            # Skip staticmethod and classmethod - they have different calling conventions
            # and wrapping them would break their behavior
            if isinstance(raw_attr, (staticmethod, classmethod)):
                continue

            attr = getattr(cls, attr_name)
            # Only instrument callable attributes that aren't classes
            if callable(attr) and not isinstance(attr, type):
                # Skip if already decorated with @step to prevent double instrumentation
                if getattr(attr, "_xray_step_decorated", False):
                    continue
                # Apply @step decorator
                decorated = step(name=attr_name, step_type=step_type)(attr)
                setattr(cls, attr_name, decorated)

        return cls

    # Support both @instrument_class and @instrument_class()
    if cls is not None:
        return decorate(cls)
    return decorate


def attach_reasoning(reasoning: dict[str, Any] | str) -> bool:
    """Attach reasoning information to the current active step.

    This is a convenience function for attaching reasoning data from anywhere
    in the call stack, as long as there's an active step. Useful inside
    decorated functions to add decision context.

    Args:
        reasoning: Dict of reasoning data or string explanation.
            If a string, it's stored as {"explanation": reasoning}.

    Returns:
        True if attached successfully, False if no active step.

    Example:
        @step(step_type="filter")
        def filter_candidates(candidates, threshold=0.5):
            filtered = [c for c in candidates if c["score"] > threshold]
            attach_reasoning({
                "threshold": threshold,
                "input_count": len(candidates),
                "output_count": len(filtered),
                "removed": len(candidates) - len(filtered),
            })
            return filtered
    """
    step_obj = current_step()
    if step_obj is None:
        return False
    step_obj.attach_reasoning(reasoning)
    return True


def attach_candidates(
    candidates: list[dict[str, Any]],
    phase: str = "output",
) -> bool:
    """Attach candidate information to the current active step.

    Convenience function for the common pattern of attaching a list
    of candidates with id/score/reason. Extracts the relevant fields
    from each candidate and stores them as reasoning.

    Args:
        candidates: List of candidate dicts (should have 'id' field).
            Supports common ID field names: id, _id, candidate_id.
        phase: "input" or "output" to indicate which phase of processing.
            Stored as {phase}_candidates in reasoning.

    Returns:
        True if attached successfully, False if no active step.

    Example:
        @step(step_type="rank")
        def rank_candidates(candidates):
            ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)
            attach_candidates(ranked, phase="output")
            return ranked
    """
    step_obj = current_step()
    if step_obj is None:
        return False

    # Extract candidate info using key existence check (not truthiness)
    # to handle falsy IDs like 0 or ""
    candidate_info = []
    for c in candidates:
        # Find ID using first existing key (handles falsy values correctly)
        id_val = None
        for key in ("id", "_id", "candidate_id"):
            if key in c:
                id_val = c[key]
                break

        info: dict[str, Any] = {"id": id_val}
        if "score" in c:
            info["score"] = c["score"]
        if "reason" in c:
            info["reason"] = c["reason"]
        candidate_info.append(info)

    step_obj.attach_reasoning({f"{phase}_candidates": candidate_info})
    return True
