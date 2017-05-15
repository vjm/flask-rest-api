"""
ETag feature

Conditional request execution using the If-Match and If-None-Match headers,
triggered by a decorator in Flask.
"""

import hashlib

import marshmallow as ma

from flask import request, current_app, json, Response
from flask.views import MethodView

from .exceptions import PreconditionRequired, NotModified
from .args_parser import abort


def is_etag_enabled(app):
    """Return True if Flask app config allows to use etag feature."""
    return app.config.get('ETAG_ENABLED', False)


def validate_etag(endpoint, schema, get_item_func=None, **kwargs):
    """Validate etag conditions in PUT, DELETE and PATCH requests

    :param endpoint: endpoint as a MethodView instance
    :param schema: ETag data schema
    :type endpoint: `MethodView <flask.MethodView>` instance or `None`
    :type schema: `Schema <marshmallow.Schema>` instance or `None`
    """
    if not isinstance(schema, ma.Schema):
        raise ValueError('Invalid schema: {}'.format(schema))

    if is_etag_enabled(current_app):
        if request.method in ('PUT', 'DELETE', 'PATCH',):
            # endpoint could be a MethodView (class) or a function
            # when get_item_func is None, try to extract it from MethodView
            if isinstance(endpoint, MethodView) and get_item_func is None:
                try:
                    get_item_func_name = '_get_item'
                    get_item_func = getattr(endpoint, get_item_func_name)
                except AttributeError:
                    raise AttributeError(
                        'Missing `{}` in {} MethodView!'.format(
                            get_item_func_name, endpoint.__class__.__name__))
            if get_item_func is None:
                # but if it still be undefined, we are screwed...
                raise AttributeError('Missing `get_item_func`!')

            item = get_item_func(**kwargs)
            etag_data = schema.dump(item)[0] if schema is not None else None
            etag_value = generate_etag(etag_data)
            if not request.if_match:
                raise PreconditionRequired
            if etag_value not in request.if_match:
                abort(412)


def process_etag(response, schema, data, validate=True):
    """Process etag in response

    :param response: endpoint response
    :param schema: ETag value schema
    :param data: ETag value is generated by combination of schema and data
    :param validate: if True ETag value from request is checked
        and a new etag is generated
    :type response: `Response <flask.Response>` instance
    :type schema: `Schema <marshmallow.Schema>` instance or `None`
    :type validate: bool
    """
    if validate:
        if not isinstance(response, Response):
            raise ValueError('Invalid response: {}'.format(response))
        if not isinstance(schema, ma.Schema):
            raise ValueError('Invalid schema: {}'.format(schema))

        if is_etag_enabled(current_app) and request.method != 'DELETE':
            etag_data = schema.dump(data)[0] if schema is not None else None
            etag_value = generate_etag(etag_data)
            if (request.method == 'GET'
                    and request.if_none_match
                    and etag_value in request.if_none_match):
                raise NotModified
            response.set_etag(etag_value)


def generate_etag(data=None):
    """Generates an etag based on data."""
    # flask's json.dumps is needed here
    # as vanilla json.dumps chokes on lazy_strings
    etag_data = json.dumps(data, sort_keys=True)
    return hashlib.sha1(bytes(etag_data, 'utf-8')).hexdigest()
