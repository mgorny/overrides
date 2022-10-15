#
#  Copyright 2019 Mikko Korpela
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import dis
import functools
import inspect
import sys
from types import FunctionType
from typing import Callable, List, Optional, Tuple, TypeVar, Union, overload

__VERSION__ = "7.2.0"

from overrides.signature import ensure_signature_is_compatible

_WrappedMethod = TypeVar("_WrappedMethod", bound=Union[FunctionType, Callable])
_DecoratorMethod = Callable[[_WrappedMethod], _WrappedMethod]


@overload
def overrides(
    method: None = None,
    *,
    check_signature: bool = True,
    check_at_runtime: bool = False,
) -> _DecoratorMethod:
    ...


@overload
def overrides(
    method: _WrappedMethod,
    *,
    check_signature: bool = True,
    check_at_runtime: bool = False,
) -> _WrappedMethod:
    ...


def overrides(
    method: Optional[_WrappedMethod] = None,
    *,
    check_signature: bool = True,
    check_at_runtime: bool = False,
) -> Union[_DecoratorMethod, _WrappedMethod]:
    """Decorator to indicate that the decorated method overrides a method in
    superclass.
    The decorator code is executed while loading class. Using this method
    should have minimal runtime performance implications.

    This is based on my idea about how to do this and fwc:s highly improved
    algorithm for the implementation fwc:s
    algorithm : http://stackoverflow.com/a/14631397/308189
    my answer : http://stackoverflow.com/a/8313042/308189

    How to use:
    from overrides import overrides

    class SuperClass(object):
        def method(self):
          return 2

    class SubClass(SuperClass):

        @override
        def method(self):
            return 1

    :param check_signature: Whether or not to check the signature of the overridden method.
    :param check_at_runtime: Whether or not to check the overridden method at runtime.
    :raises AssertionError: if no match in super classes for the method name
    :return: method with possibly added (if the method doesn't have one)
        docstring from super class
    """
    if method is not None:
        return _overrides(method, check_signature, check_at_runtime)
    else:
        return functools.partial(
            overrides,
            check_signature=check_signature,
            check_at_runtime=check_at_runtime,
        )


def _overrides(
    method: _WrappedMethod, check_signature: bool, check_at_runtime: bool,
) -> _WrappedMethod:
    setattr(method, "__override__", True)
    global_vars = getattr(method, "__globals__", None)
    if global_vars is None:
        global_vars = vars(sys.modules[method.__module__])
    for super_class in _get_base_classes(sys._getframe(3), global_vars):
        if hasattr(super_class, method.__name__):
            if check_at_runtime:

                @functools.wraps(method)
                def wrapper(*args, **kwargs):
                    _validate_method(method, super_class, check_signature)
                    return method(*args, **kwargs)

                return wrapper  # type: ignore
            else:
                _validate_method(method, super_class, check_signature)
                return method
    raise TypeError(f"{method.__qualname__}: No super class method found")


def _validate_method(method, super_class, check_signature):
    super_method = getattr(super_class, method.__name__)
    is_static = isinstance(
        inspect.getattr_static(super_class, method.__name__), staticmethod
    )
    if getattr(super_method, "__final__", False):
        raise TypeError(f"{method.__name__}: is finalized in {super_class}")
    if not method.__doc__:
        method.__doc__ = super_method.__doc__
    if (
        check_signature
        and not method.__name__.startswith("__")
        and not isinstance(super_method, property)
    ):
        ensure_signature_is_compatible(super_method, method, is_static)


def _get_base_classes(frame, namespace):
    return [
        _get_base_class(class_name_components, namespace)
        for class_name_components in _get_base_class_names(frame)
    ]


def _get_base_class_names(frame) -> List[List[str]]:
    """Get baseclass names from the code object"""
    extends: List[Tuple[str, str]] = []
    add_last_step = True
    for instruction in dis.get_instructions(frame.f_code):
        if instruction.offset > frame.f_lasti:
            break
        if instruction.opcode not in dis.hasname:
            continue
        if not add_last_step:
            extends = []
            add_last_step = True
        if instruction.opname == "LOAD_NAME":
            extends.append(("name", instruction.argval))
        elif instruction.opname == "LOAD_ATTR":
            extends.append(("attr", instruction.argval))
        elif instruction.opname == "LOAD_GLOBAL":
            extends.append(("name", instruction.argval))
        else:
            add_last_step = False

    items: List[List[str]] = []
    previous_item: List[str] = []
    for t, s in extends:
        if t == "name":
            if previous_item:
                items.append(previous_item)
            previous_item = [s]
        else:
            previous_item += [s]
    if previous_item:
        items.append(previous_item)
    return items


def _get_base_class(components, namespace):
    try:
        obj = namespace[components[0]]
    except KeyError:
        if isinstance(namespace["__builtins__"], dict):
            obj = namespace["__builtins__"][components[0]]
        else:
            obj = getattr(namespace["__builtins__"], components[0])
    for component in components[1:]:
        if hasattr(obj, component):
            obj = getattr(obj, component)
    return obj
