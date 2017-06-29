import copy

from hamcrest.core.matcher import Matcher
from typing import Union, Callable, Any

from proxy.parser.http_parser import HttpResponse, HttpRequest
from proxy.pipe.recipe.matchers import LambdaMatcher


class DoesNotAccept(Exception):
    pass


class Transform(object):
    def transform_request(self, request, proxy: "Flow") -> HttpRequest:
        return request

    def transform_response(self, request, response, original_request, proxy: "Flow") -> HttpResponse:
        return response

    def transform(self, request, proxy: "Flow", next_in_chain):
        new_request = self.transform_request(request, proxy)
        if not new_request:
            raise DoesNotAccept()

        response = yield from next_in_chain(new_request)

        response = self.transform_response(new_request, response, request, proxy)

        return response


class Flow:
    def __init__(self, parameters=None):
        self.__branches = []
        self.__parameters = parameters

    @property
    def parameters(self):
        return self.__parameters

    @parameters.setter
    def parameters(self, parameters):
        self.__parameters = parameters
        for branch in self.__branches:
            if hasattr(branch, "parameters"):
                branch.parameters = parameters

    def __get__(self, instance, owner):
        if not instance:
            return self

        new_flow = instance.__dict__.get("__flow", None)
        if new_flow is not None:
            return new_flow

        new_flow = copy.copy(self)
        new_flow.__branches = []
        for branch in self.__branches:
            if hasattr(branch, "__get__"):
                new_flow.__branches.append(branch.__get__(instance, owner))
            else:
                new_flow.__branches.append(branch)

        instance.__dict__["__flow"] = new_flow
        return new_flow

    def when(self, matcher: Union[Matcher, Callable[[Any], bool]]) -> "Flow":
        if callable(matcher):
            matcher = LambdaMatcher(matcher)

        flow = GuardedFlow(matcher, self.__parameters)
        return self.then_delegate(flow)

    def transform(self, transform: Transform):
        flow = TransformingFlow(transform, self.__parameters)
        return self.then_delegate(flow)

    def __call__(self, request: HttpRequest):
        for branch in self.__branches:
            try:
                response = yield from branch(request)
                return response
            except DoesNotAccept:
                pass

        raise DoesNotAccept()

    def then_respond(self, responder):
        if callable(responder):
            def _responder(*args):
                yield from []  # Needed as the result must be a generator
                response = responder(*args)
                return response
        else:
            def _responder(*args):
                yield from []  # Needed as the result must be a generator
                return responder

        self.__branches.append(_responder)
        return self

    def then_pass_through(self, endpoint="remote"):
        def _responder(self, request=None):
            if not request: request = self  # The method can be bound or not bound
            response = yield endpoint, request
            return response

        self.__branches.append(_responder)
        return self

    def then_delegate(self, flow):
        self.__branches.append(flow)
        flow.parameters = self.parameters
        return flow

    def respond_when(self, matcher):
        return self.when(matcher).then_respond


class GuardedFlow(Flow):
    def __init__(self, guard, parameters=None):
        super().__init__(parameters)
        self.__guard = guard

    def __call__(self, request: HttpRequest):
        if not self.__guard.matches(request):
            raise DoesNotAccept()

        return super().__call__(request)


class TransformingFlow(Flow):
    def __init__(self, transform, parameters=None):
        super().__init__(parameters)
        self.__transform = transform

    def __call__(self, request: HttpRequest):
        super_call = super().__call__
        return self.__transform.transform(request, self, super_call)
