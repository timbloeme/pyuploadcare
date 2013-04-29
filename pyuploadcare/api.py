# coding: utf-8
"""
Uploadcare REST client.

It is JSON REST request abstraction layer that is used by the
``pyuploadcare.api_resources``.

"""

from __future__ import unicode_literals
import email.utils
import hashlib
import hmac
import re
import logging
import json

import requests
import six

if six.PY3:
    from urllib.parse import urljoin, urlsplit
else:
    from urlparse import urljoin, urlsplit

from . import conf, __version__
from .exceptions import (
    APIConnectionError, AuthenticationError, APIError, InvalidRequestError,
)


logger = logging.getLogger("pyuploadcare")


def rest_request(verb, path, data=None):
    """Makes REST API request and returns response as ``dict``.

    It provides auth headers as well and takes settings from ``conf`` module.

    Make sure that given ``path`` does not contain leading slash.

    Usage example::

        >>> rest_request('GET', 'files/?limit=10')
        {
            'next': 'https://api.uploadcare.com/files/?limit=10&page=2',
            'total': 1241,
            'page': 1,
            'pages': 125,
            'per_page': 10,
            'previous': None,
            'results': [
                # ...
                {
                    # ...
                    'uuid': 1921953c-5d94-4e47-ba36-c2e1dd165e1a,
                    # ...
                },
                # ...
            ]
        }

    """
    assert not path.startswith('/'), path
    url = urljoin(conf.api_base, path)
    url_parts = urlsplit(url)

    if url_parts.query:
        path = url_parts.path + '?' + url_parts.query
    else:
        path = url_parts.path

    content = ''
    if data is not None:
        content = json.dumps(data)

    content_type = 'application/json'
    content_md5 = hashlib.md5(content.encode('utf-8')).hexdigest()
    date = email.utils.formatdate(usegmt=True)

    sign_string = '\n'.join([
        verb,
        content_md5,
        content_type,
        date,
        path,
    ])
    sign_string_as_bytes = sign_string.encode('utf-8')

    try:
        secret_as_bytes = conf.secret.encode('utf-8')
    except AttributeError:
        secret_as_bytes = bytes()
    sign = hmac.new(secret_as_bytes, sign_string_as_bytes, hashlib.sha1) \
        .hexdigest()

    headers = {
        'Authorization': 'Uploadcare {0}:{1}'.format(conf.pub_key, sign),
        'Date': date,
        'Content-Type': content_type,
        'Content-Length': six.text_type(len(content)),
        'Accept': 'application/vnd.uploadcare-v{0}+json'.format(conf.api_version),
        'User-Agent': 'pyuploadcare/{0}'.format(__version__),
    }
    logger.debug('''sent:
        verb: {0}
        path: {1}
        headers: {2}
        data: {3}'''.format(verb, path, headers, content))

    try:
        response = requests.request(verb, url, allow_redirects=True,
                                    verify=conf.verify_api_ssl,
                                    headers=headers, data=content)
    except requests.RequestException as exc:
        raise APIConnectionError(exc.args[0])

    logger.debug(
        'got: {0} {1}'.format(response.status_code, response.content)
    )

    if 'warning' in response.headers:
        match = re.search('"(.+)"', response.headers['warning'])
        if match:
            for warning in match.group(1).split('; '):
                logger.warn('API Warning: {0}'.format(warning))

    # TODO: Add check for content-type.
    if response.status_code == 200:
        try:
            return response.json()
        except ValueError as exc:
            raise APIError(exc.args[0])
    # No content.
    if response.status_code == 204:
        return

    if response.status_code == 403:
        raise AuthenticationError(response.content)

    if response.status_code in (400, 404):
        raise InvalidRequestError(response.content)

    raise APIError(response.content)


def uploading_request(verb, path, data=None, files=None):
    """Makes Uploading API request and returns response as ``dict``.

    It takes settings from ``conf`` module.

    Make sure that given ``path`` does not contain leading slash.

    Usage example::

        >>> file_obj = open('photo.jpg', 'rb')
        >>> uploading_request('POST', 'base/', files={'file': file_obj})
        {
            'file': '9b9f4483-77b8-40ae-a198-272ba6280004'
        }
        >>> File('9b9f4483-77b8-40ae-a198-272ba6280004')

    """
    assert not path.startswith('/'), path
    url = urljoin(conf.upload_base, path)

    if data is None:
        data = {}
    data['pub_key'] = conf.pub_key
    data['UPLOADCARE_PUB_KEY'] = conf.pub_key

    try:
        response = requests.request(
            verb, url, allow_redirects=True, verify=conf.verify_upload_ssl,
            data=data, files=files
        )
    except requests.RequestException as exc:
        raise APIConnectionError(exc.args[0])

    if response.status_code == 200:
        try:
            return response.json()
        except ValueError as exc:
            raise APIError(exc.args[0])

    if response.status_code in (400, 404):
        raise InvalidRequestError(response.content)

    raise APIError(response.content)
