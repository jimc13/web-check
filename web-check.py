#!/usr/bin/env python3
try:
    import sys
    import re
    import json
    import argparse
    import time
    import requests
    import html2text
    import hashlib
    import difflib
    import sqlalchemy
    from sqlalchemy import Column, Integer, String, Table, MetaData
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
except ImportError:
    print("""Import failed make sure you have set up the virtual enviroment.
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt""")
    exit(1)

def get_text(html):
    """
    Input html.  Returns utf-8 markdown without links

    requests.get().text will be used as the input data
    html2text will be used to remove most of the changing parts of the response
    links will be ignored since most large sites have dynamic links
    if you want to closely monitor a basic site it is probably better to hash
    requests.get().content and not bother stripping the html
    """
    h = html2text.HTML2Text()
    h.ignore_links = True
    return h.handle(html)

def get_md5(html):
    """
    Input html. Returns MD5 hash of the text.
    """
    return hashlib.md5(get_text(html).encode('utf-8')).hexdigest()

def failed_connection(check, session):
    current_time = time.time()
    if not check.failed_since:
        check.failed_since = current_time
        session.commit()
    if current_time - check.failed_since >= check.max_down_time:
        print('Warning: Can\'t connect to {}'.format(check.url))

    return ''

def check_if_recovered(check, session):
    if not check.failed_since:
        return ''
    check.failed_since = 0
    session.commit()
    last_run = check.run_after - check.check_frequency
    if last_run - check.failed_since >= check.max_down_time:
        print('Reastablished connection to {}'.format(check.url))

    return ''

def run_checks():
    """Perform hash, string, difference and raw checks for all stored url's"""
    for check in session.query(MD5Check).filter(MD5Check.run_after <
                    time.time()).order_by(MD5Check.id):
        check.run_after = time.time() + check.check_frequency
        session.commit()
        try:
            url_content = requests.get(check.url, timeout=check.check_timeout)
        except requests.exceptions.ConnectionError:
            failed_connection(check, session)
            continue

        if url_content.status_code != 200:
            failed_connection(check, session)
            continue

        check_if_recovered(check, session)
        try:
            new_hash = get_md5(url_content.text)
        except:
            print('Error: Failed to hash response from {}'.format(check.url))
            continue

        if new_hash != check.current_hash:
            if new_hash == check.old_hash:
                print('The md5 for {} has been reverted'.format(check.url))
            else:
                print('The md5 for {} has changed'.format(check.url))

            check.old_hash = check.current_hash
            check.current_hash = new_hash
            session.commit()

    for check in session.query(StringCheck).filter(StringCheck.run_after <
                    time.time()).order_by(StringCheck.id):
        check.run_after = time.time() + check.check_frequency
        session.commit()
        try:
            url_content = requests.get(check.url, timeout=check.check_timeout)
        except requests.exceptions.ConnectionError:
            failed_connection(check, session)
            continue

        if url_content.status_code != 200:
            failed_connection(check, session)
            continue

        check_if_recovered(check, session)
        string_found = check.string_to_match in get_text(url_content.text)
        if string_found != check.present:
            if check.present:
                print('{} is no longer present on {}'.format(
                                                        check.string_to_match,
                                                        check.url))
                check.present = 0
            else:
                print('{} is now present on {}'.format(check.string_to_match,
                                                    check.url))
                check.present = 1

            session.commit()

    for check in session.query(DiffCheck).filter(DiffCheck.run_after <
                    time.time()).order_by(DiffCheck.id):
        check.run_after = time.time() + check.check_frequency
        session.commit()
        try:
            url_content = requests.get(check.url, timeout=check.check_timeout)
        except requests.exceptions.ConnectionError:
            failed_connection(check, session)
            continue

        if url_content.status_code != 200:
            failed_connection(check, session)
            continue

        check_if_recovered(check, session)
        text = get_text(url_content.text)
        if text != check.current_content:
            for line in difflib.context_diff(check.current_content.split('\n'),
                            text.split('\n'),
                            fromfile='Old content for {}'.format(check.url),
                            tofile='New content for {}'.format(check.url)):
                print(line)
            check.current_content = text
            session.commit()

    for check in session.query(RawCheck).filter(RawCheck.run_after <
                    time.time()).order_by(RawCheck.id):
        check.run_after = time.time() + check.check_frequency
        session.commit()
        try:
            url_content = requests.get(check.url, timeout=check.check_timeout)
        except requests.exceptions.ConnectionError:
            failed_connection(check, session)
            continue

        if url_content.status_code != 200:
            failed_connection(check, session)
            continue

        check_if_recovered(check, session)
        try:
            new_hash = hashlib.md5(url_content.text.encode('utf-8')).hexdigest()
        except:
            print('Error: Failed to hash response from {}'.format(check.url))
            continue

        if new_hash == check.current_hash:
            continue

        check.old_hash = check.current_hash
        session.commit()
        try:
            m = re.search(check.expression, url_content.text, re.S)
        except:
            # I couldn't catch the sre_constants.error I'm looking for so...
            print('Error: invalid regular expression')
            continue

        try:
            capture_groups = m.groups()
        except AttributeError:
            print('Error: no matches for regular expression on {}'.format(url))
            continue

        try:
            old_capture_groups = tuple(json.loads(check.capture_groups))
        except:
            print('Error: could not retreive data for raw check of {}'.format(
                                                                    check.url))
            continue

        if capture_groups == old_capture_groups:
            continue

        print('RawCheck with expression {} changed for {}').format(
                                                            check.expression,
                                                            check.url)
        for count, old_capture_group in enumerate(old_capture_groups):
            if old_capture_group != capture_groups[count]:
                print('{} has been changed to {}'.format(old_capture_group,
                                                    capture_groups[count]))

        check.capture_groups = json.dumps(capture_groups)
        session.commit()

    return ''

def validate_input(max_down_time, check_frequency, check_timeout):
    """
    Check's integers are given and that check_timeout is positive.

    Negative max_down_time and check_frequency values have no purpose but are
    still a valid input.  The check would run each time the script is called and
    alert if a connection failed, values of 0 will have the same effect.
    """
    try:
        max_down_time = int(max_down_time)
    except ValueError:
        print('Error: max_down_time {} given, must be an integer'.format(
                                                                max_down_time))
        exit(1)

    try:
        check_frequency = int(check_frequency)
    except ValueError:
        print('Error: check_frequency {} given, must be an integer'.format(
                                                            check_frequency))
        exit(1)

    try:
        check_timeout = int(check_timeout)
    except ValueError:
        print('Error: check_timeout {} given, must be an integer'.format(
                                                                check_timeout))
        exit(1)

    if not check_timeout > 0:
        print('Error: check-timeout {} given, must be greater than 0'.format(
                                                                check_timeout))
        exit(1)

    return (max_down_time, check_frequency, check_timeout)

def add_md5(url, max_down_time, check_frequency, check_timeout):
    """
    Add a database entry for a url to monitor the md5 hash of.  Returns message
    relating to success.
    """
    max_down_time, check_frequency, check_timeout = validate_input(
        max_down_time, check_frequency, check_timeout)
    try:
        url_content = requests.get(url, timeout=check_timeout)
    except requests.exceptions.ConnectionError:
        return 'Error: Could not connect to chosen url {}'.format(url)
    except requests.exceptions.MissingSchema as e:
        return e
    except requests.exceptions.InvalidSchema as e:
        return e

    if url_content.status_code != 200:
        return 'Error: {} code from server'.format(url_content.status_code)

    try:
        current_hash = get_md5(url_content.text)
    except:
        return 'Error: Failed to hash response from {}'.format(url)
    check = MD5Check(url=url,
                current_hash=current_hash,
                failed_since=0,
                max_down_time=max_down_time,
                run_after=0,
                check_frequency=check_frequency,
                check_timeout=check_timeout)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        session.rollback()
        return 'Error: An entry for {} is already in database'.format(url)
    else:
        return 'Added MD5 Check for {}'.format(url)

def add_string(url, string, max_down_time, check_frequency, check_timeout):
    """
    Add a database entry for a url to monitor for a string.  Returns message
    relating to success.
    """
    max_down_time, check_frequency, check_timeout = validate_input(
        max_down_time, check_frequency, check_timeout)
    try:
        url_content = requests.get(url, timeout=check_timeout)
    except requests.exceptions.ConnectionError:
        return 'Error: Could not connect to chosen url {}'.format(url)
    except requests.exceptions.MissingSchema as e:
        return e
    except requests.exceptions.InvalidSchema as e:
        return e

    if url_content.status_code != 200:
        return 'Error: {} code from server'.format(url_content.status_code)

    string_exists = 0
    if string in get_text(url_content.text):
        string_exists = 1

    check = StringCheck(url=url,
                    string_to_match=string,
                    present=string_exists,
                    failed_since=0,
                    max_down_time=max_down_time,
                    run_after= 0,
                    check_frequency=check_frequency,
                    check_timeout=check_timeout)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        session.rollback()
        return 'Error: An entry for {} is already in database'.format(url)
    else:
        if string_exists:
            print('{} is currently present, will alert if this changes'.format(
                                                                    string))
        else:
            print('{} is currently not present, will alert if this changes'
.format(string))

        return 'Added String Check for {}'.format(url)

def add_diff(url, max_down_time, check_frequency, check_timeout):
    """
    Add a database entry for a url to monitor for any text changes.
    Returns message relating to success.
    """
    max_down_time, check_frequency, check_timeout = validate_input(
        max_down_time, check_frequency, check_timeout)
    try:
        url_content = requests.get(url, timeout=check_timeout)
    except requests.exceptions.ConnectionError:
        return 'Error: Could not connect to chosen url {}'.format(url)
    except requests.exceptions.MissingSchema as e:
        return e
    except requests.exceptions.InvalidSchema as e:
        return e

    if url_content.status_code != 200:
        return 'Error: {} code from server'.format(url_content.status_code)

    check = DiffCheck(url=url,
                    current_content=get_text(url_content.text),
                    failed_since=0,
                    max_down_time=max_down_time,
                    run_after=0,
                    check_frequency=check_frequency,
                    check_timeout=check_timeout)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        session.rollback()
        return 'Error: An entry for {} is already in database'.format(url)
    else:
        return 'Added Diff Check for {}'.format(url)

def add_raw(url, expression, max_down_time, check_frequency, check_timeout):
    """
    Add a database entry for a url to monitor for a change using regex.
    Returns message relating to success.
    """
    max_down_time, check_frequency, check_timeout = validate_input(
        max_down_time, check_frequency, check_timeout)
    try:
        url_content = requests.get(url, timeout=check_timeout)
    except requests.exceptions.ConnectionError:
        return 'Error: Could not connect to chosen url {}'.format(url)
    except requests.exceptions.MissingSchema as e:
        return e
    except requests.exceptions.InvalidSchema as e:
        return e

    if url_content.status_code != 200:
        return 'Error: {} code from server'.format(url_content.status_code)

    try:
        # Not sure if I want to hash .text.encode('utf-8') or .content
        current_hash = hashlib.md5(url_content.text.encode('utf-8')).hexdigest()
    except:
        return 'Error: Failed to hash response from {}'.format(url)

    try:
        m = re.search(expression, url_content.text, re.S)
    except:
        # I couldn't catch the sre_constants.error I'm looking for so...
        return 'Error: invalid regular expression'

    try:
        capture_groups = m.groups()
    except AttributeError:
        return 'Error: no matches for regular expression on {}'.format(url)

    json_capture_groups = json.dumps(capture_groups)
    check = RawCheck(url=url,
                expression=expression,
                current_hash=current_hash,
                capture_groups=json_capture_groups,
                failed_since=0,
                max_down_time=max_down_time,
                run_after=0,
                check_frequency=check_frequency,
                check_timeout=check_timeout)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        session.rollback()
        return 'Error: An entry for {} is already in database'.format(url)
    else:
        for count, capture_group in enumerate(capture_groups):
            print('{} matched capture group {}, will alert if this changes'.format(
                                                                    capture_group,
                                                                    count))

        return 'Added Raw Check for {}'.format(url)

def get_longest_md5():
    longest_url = 3
    longest_current_hash = 12
    longest_old_hash = 8
    longest_failed_since = 12
    longest_max_down_time = 14
    longest_run_after = 9
    longest_check_frequency = 15
    longest_check_timeout = 13
    for check in session.query(MD5Check).order_by(MD5Check.id):
        if len(str(check.url)) > longest_url:
            longest_url = len(str(check.url))
        if len(str(check.current_hash)) > longest_current_hash:
            longest_current_hash = len(str(check.current_hash))
        if len(str(check.old_hash)) > longest_old_hash:
            longest_old_hash = len(str(check.old_hash))
        if len(str(check.failed_since)) > longest_failed_since:
            longest_failed_since = len(str(check.failed_since))
        if len(str(check.max_down_time)) > longest_max_down_time:
            longest_max_down_time = len(str(check.max_down_time))
        if len(str(check.run_after)) > longest_run_after:
            longest_run_after = len(str(check.run_after))
        if len(str(check.check_frequency)) > longest_check_frequency:
            longest_check_frequency = len(str(check.check_frequency))
        if len(str(check.check_timeout)) > longest_check_timeout:
            longest_check_timeout = len(str(check.check_timeout))

    return (('url', longest_url),
        ('current_hash', longest_current_hash),
        ('old_hash', longest_old_hash),
        ('failed_since', longest_failed_since),
        ('max_down_time', longest_max_down_time),
        ('run_after', longest_run_after),
        ('check_frequency', longest_check_frequency),
        ('check_timeout', longest_check_timeout))

def get_longest_string():
    longest_url = 3
    longest_string_to_match = 15
    longest_present = 7
    longest_failed_since = 12
    longest_max_down_time = 14
    longest_run_after = 9
    longest_check_frequency = 15
    longest_check_timeout = 13
    for check in session.query(StringCheck).order_by(StringCheck.id):
        if len(str(check.url)) > longest_url:
            longest_url = len(str(check.url))
        if len(str(check.string_to_match)) > longest_string_to_match:
            longest_string_to_match = len(str(check.string_to_match))
        if len(str(check.present)) > longest_present:
            longest_present = len(str(check.present))
        if len(str(check.failed_since)) > longest_failed_since:
            longest_failed_since = len(str(check.failed_since))
        if len(str(check.max_down_time)) > longest_max_down_time:
            longest_max_down_time = len(str(check.max_down_time))
        if len(str(check.run_after)) > longest_run_after:
            longest_run_after = len(str(check.run_after))
        if len(str(check.check_frequency)) > longest_check_frequency:
            longest_check_frequency = len(str(check.check_frequency))
        if len(str(check.check_timeout)) > longest_check_timeout:
            longest_check_timeout = len(str(check.check_timeout))

    return (('url', longest_url),
        ('string_to_match', longest_string_to_match),
        ('present', longest_present),
        ('failed_since', longest_failed_since),
        ('max_down_time', longest_max_down_time),
        ('run_after', longest_run_after),
        ('check_frequency', longest_check_frequency),
        ('check_timeout', longest_check_timeout))

def get_longest_diff():
    """
    Called by list_checks to check how much to pad the tables.
    """
    longest_url = 3
    longest_current_content = 15
    longest_failed_since = 12
    longest_max_down_time = 14
    longest_run_after = 9
    longest_check_frequency = 15
    longest_check_timeout = 13
    for check in session.query(DiffCheck).order_by(DiffCheck.id):
        if len(str(check.url)) > longest_url:
            longest_url = len(str(check.url))
        # Not checking how long current_content is since it will be long and
        # make the table look silly
        #if len(str(check.current_content)) > longest_current_content:
        #    longest_current_content = len(str(check.current_content))
        if len(str(check.failed_since)) > longest_failed_since:
            longest_failed_since = len(str(check.failed_since))
        if len(str(check.max_down_time)) > longest_max_down_time:
            longest_max_down_time = len(str(check.max_down_time))
        if len(str(check.run_after)) > longest_run_after:
            longest_run_after = len(str(check.run_after))
        if len(str(check.check_frequency)) > longest_check_frequency:
            longest_check_frequency = len(str(check.check_frequency))
        if len(str(check.check_timeout)) > longest_check_timeout:
            longest_check_timeout = len(str(check.check_timeout))

    return (('url', longest_url),
        ('current_content', longest_current_content),
        ('failed_since', longest_failed_since),
        ('max_down_time', longest_max_down_time),
        ('run_after', longest_run_after),
        ('check_frequency', longest_check_frequency),
        ('check_timeout', longest_check_timeout))

def get_longest_raw():
    longest_url = 3
    longest_expression = 10
    longest_current_hash = 12
    longest_capture_groups = 14
    longest_failed_since = 12
    longest_max_down_time = 14
    longest_run_after = 9
    longest_check_frequency = 15
    longest_check_timeout = 13
    for check in session.query(RawCheck).order_by(RawCheck.id):
        if len(str(check.url)) > longest_url:
            longest_url = len(str(check.url))
        if len(str(check.expression)) > longest_expression:
            longest_expression = len(str(check.expression))
        if len(str(check.current_hash)) > longest_current_hash:
            longest_current_hash = len(str(check.current_hash))
        if len(str(check.capture_groups)) > longest_capture_groups:
            longest_capture_groups = len(str(check.capture_groups))
        if len(str(check.failed_since)) > longest_failed_since:
            longest_failed_since = len(str(check.failed_since))
        if len(str(check.max_down_time)) > longest_max_down_time:
            longest_max_down_time = len(str(check.max_down_time))
        if len(str(check.run_after)) > longest_run_after:
            longest_run_after = len(str(check.run_after))
        if len(str(check.check_frequency)) > longest_check_frequency:
            longest_check_frequency = len(str(check.check_frequency))
        if len(str(check.check_timeout)) > longest_check_timeout:
            longest_check_timeout = len(str(check.check_timeout))

    return (('url', longest_url),
        ('expression', longest_expression),
        ('current_hash', longest_current_hash),
        ('capture_groups', longest_capture_groups),
        ('failed_since', longest_failed_since),
        ('max_down_time', longest_max_down_time),
        ('run_after', longest_run_after),
        ('check_frequency', longest_check_frequency),
        ('check_timeout', longest_check_timeout))

def list_checks():
    """
    List all of the checks from the database in a table like format.
    """
    table_skel = '|'
    columns = []
    arguments = []
    for column, longest_entry in get_longest_md5():
        table_skel += (' {{: <{}}} |'.format(longest_entry))
        columns.append(column)
        arguments.append('row.{}'.format(column))

    print('{} Checks:'.format('MD5Check'))
    print(table_skel.format(*columns))
    for check in session.query(MD5Check).order_by(MD5Check.id):
        print(table_skel.format(str(check.url),
                        str(check.current_hash),
                        str(check.old_hash),
                        str(check.failed_since),
                        str(check.max_down_time),
                        str(check.run_after),
                        str(check.check_frequency),
                        str(check.check_timeout)))

    table_skel = '|'
    columns = []
    arguments = []
    for column, longest_entry in get_longest_string():
        table_skel += (' {{: <{}}} |'.format(longest_entry))
        columns.append(column)
        arguments.append('row.{}'.format(column))

    print('{} Checks:'.format('StringCheck'))
    print(table_skel.format(*columns))
    for check in session.query(StringCheck).order_by(StringCheck.id):
        print(table_skel.format(str(check.url),
                        str(check.string_to_match),
                        str(check.present),
                        str(check.failed_since),
                        str(check.max_down_time),
                        str(check.run_after),
                        str(check.check_frequency),
                        str(check.check_timeout)))

    table_skel = '|'
    columns = []
    arguments = []
    for column, longest_entry in get_longest_diff():
        table_skel += (' {{: <{}}} |'.format(longest_entry))
        columns.append(column)
        arguments.append('row.{}'.format(column))

    print('{} Checks:'.format('DiffCheck'))
    print(table_skel.format(*columns))
    for check in session.query(DiffCheck).order_by(DiffCheck.id):
        print(table_skel.format(str(check.url),
                            str(check.current_content),
                            str(check.failed_since),
                            str(check.max_down_time),
                            str(check.run_after),
                            str(check.check_frequency),
                            str(check.check_timeout)))

    table_skel = '|'
    columns = []
    arguments = []
    for column, longest_entry in get_longest_raw():
        table_skel += (' {{: <{}}} |'.format(longest_entry))
        columns.append(column)
        arguments.append('row.{}'.format(column))

    print('{} Checks:'.format('RawCheck'))
    print(table_skel.format(*columns))
    for check in session.query(RawCheck).order_by(RawCheck.id):
        print(table_skel.format(str(check.url),
                            str(check.expression),
                            str(check.current_hash),
                            str(check.capture_groups),
                            str(check.failed_since),
                            str(check.max_down_time),
                            str(check.run_after),
                            str(check.check_frequency),
                            str(check.check_timeout)))

    return ''

def delete_check(check_type, url):
    if check_type == 'md5':
        check = session.query(MD5Check).filter(MD5Check.url == url)
    elif check_type == 'string':
        check = session.query(StringCheck).filter(StringCheck.url == url)
    elif check_type == 'diff':
        check = session.query(DiffCheck).filter(DiffCheck.url == url)
    elif check_type == 'raw':
        check = session.query(RawCheck).filter(RawCheck.url == url)
    else:
        return 'Chose either md5, string, diff or raw check'

    if check.delete():
        session.commit()
        return '{} check for {} removed'.format(check_type, url)

    return 'There is no {} check for {}'.format(check_type, url)

def import_from_file(import_file):
    """
    Add's new database entrys from a file
    """
    error_message = 'Import failed: {} is not formatted correctly'
    with open(import_file, 'r') as f:
        for line in f:
            line = line.split('#', 1)[0].rstrip()
            if not line:
                continue
            try:
                check_type, data = line.split('|', 1)
            except ValueError:
                return error_message.format(line)

            max_down_time = default_max_down_time
            check_frequency = default_check_frequency
            check_timeout = default_check_timeout
            if check_type == 'md5':
                # There are two accepted line formats:
                # check_type|url|max_down_time|check_frequency|check_timeout
                # and check_type|url
                if '|' in data:
                    try:
                        url, max_down_time, check_frequency, check_timeout\
                        = data.split('|')
                    except ValueError:
                        return error_message.format(line)

                else:
                    url = data

                print(add_md5(url, max_down_time, check_frequency,
                        check_timeout))
            elif check_type == 'string':
                # There are two accepted line formats:
                # check_type|url|string_to_check|max_down_time|check_frequency
                # |check_timeout
                # and check_type|url
                try:
                    string_to_check, data = data.split('|', 1)
                except ValueError:
                    return error_message.format(line)
                if '|' in data:
                    try:
                        url, max_down_time, check_frequency, check_timeout\
                        = data.split('|')
                    except ValueError:
                        return error_message.format(line)

                else:
                    url = data

                print(add_string(url, string_to_check, max_down_time,
                        check_frequency, check_timeout))
            elif check_type == 'diff':
                # There are two accepted line formats:
                # check_type|url|max_down_time|check_frequency|check_timeout
                # and check_type|url
                if '|' in data:
                    try:
                        url, max_down_time, check_frequency, check_timeout\
                        = data.split('|')
                    except ValueError:
                        return error_message.format(line)

                else:
                    url = data

                print(add_diff(url, max_down_time, check_frequency,
                        check_timeout))
            elif check_type == 'raw':
                try:
                    expression, data = data.split('|', 1)
                except ValueError:
                    return error_message.format(line)
                if '|' in data:
                    try:
                        url, max_down_time, check_frequency, check_timeout\
                        = data.split('|')
                    except ValueError:
                        return error_message.format(line)

                else:
                    url = data

                print(add_raw(url, expression, max_down_time,
                        check_frequency, check_timeout))
            else:
                return error_message.format(line)

    return ''


if __name__ == '__main__':
    default_max_down_time = 86400
    default_check_frequency = 3600
    default_check_timeout = 30
    default_database_location = 'web_checks.db'
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--check', action='store_true',
        help='Run checks against all monitored urls')
    parser.add_argument('-l', '--list', action='store_true',
        help='Maximum number of set string that can occur')
    parser.add_argument('-d', '--delete', nargs=2,
        help='The entry to delete id must be used')
    parser.add_argument('-a', '--add', nargs='+',
        help='The type of check to setup and what url to check against')
    parser.add_argument('--max-down-time', type=int,
        default=default_max_down_time,
        help='Number of seconds a site can be down for before warning')
    parser.add_argument('--check-frequency', type=int,
        default=default_check_frequency,
        help='Specify the number of seconds to check after')
    parser.add_argument('--check-timeout', type=int,
        default=default_check_timeout,
        help='Specify the number of seconds to check_timeout after')
    parser.add_argument('--database-location',
        default=default_database_location,
        help='Specify a database name and location')
    parser.add_argument('--import-file',
        help='Chose a file to populate the database from')
    parser.allow_abbrev = False
    args = parser.parse_args()

    engine = sqlalchemy.create_engine('sqlite:///{}'.format(
                                                    args.database_location))
    Base = declarative_base()
    metadata = MetaData()

    class MD5Check(Base):
        __tablename__ = 'md5s'
        id = Column(Integer, primary_key=True)
        url = Column(String, unique=True)
        current_hash = Column(String)
        old_hash = Column(String)
        failed_since = Column(Integer)
        max_down_time = Column(Integer)
        run_after = Column(Integer)
        check_frequency = Column(Integer)
        check_timeout = Column(Integer)
        def __repr__(self):
            return '<url(url={}, current_hash={}, old_hash={},\
failed_since={}, max_down_time={}, run_after={},\
check_frequency={}, check_timeout{})>'.format(
                        self.url,
                        self.current_hash,
                        self.old_hash,
                        self.failed_since,
                        self.max_down_time,
                        self.run_after,
                        self.check_frequency,
                        self.check_timeout)

    class StringCheck(Base):
        __tablename__ = 'strings'
        id = Column(Integer, primary_key=True)
        url = Column(String)
        string_to_match = Column(String)
        present = Column(Integer)
        failed_since = Column(Integer)
        max_down_time = Column(Integer)
        run_after = Column(Integer)
        check_frequency = Column(Integer)
        check_timeout = Column(Integer)
        def __repr__(self):
            return '<url(url={}, string_to_match={}, present={},\
failed_since={}, max_down_time={}, run_after={},\
check_frequency={}, check_timeout{})>'.format(
                        self.url,
                        self.string_to_match,
                        self.present,
                        self.failed_since,
                        self.max_down_time,
                        self.run_after,
                        self.check_frequency,
                        self.check_timeout)

    class DiffCheck(Base):
        __tablename__ = 'diffs'
        id = Column(Integer, primary_key=True)
        url = Column(String)
        current_content = Column(String)
        failed_since = Column(Integer)
        max_down_time = Column(Integer)
        run_after = Column(Integer)
        check_frequency = Column(Integer)
        check_timeout = Column(Integer)
        def __repr__(self):
            return '<url(url={}, current_content={}, failed_since=\
{}, max_down_time={}, run_after={},\
check_frequency={})>'.format(
                            self.url,
                            self.string_to_match,
                            self.failed_since,
                            self.max_down_time,
                            self.run_after,
                            self.check_frequency,
                            self.check_timeout)

    class RawCheck(Base):
        __tablename__ = 'raws'
        id = Column(Integer, primary_key=True)
        url = Column(String)
        expression = Column(String)
        current_hash = Column(String)
        capture_groups = Column(String)
        failed_since = Column(Integer)
        max_down_time = Column(Integer)
        run_after = Column(Integer)
        check_frequency = Column(Integer)
        check_timeout = Column(Integer)
        def __repr__(self):
            return '<url(url={}, expression={}, current_hash={},\
capture_groups={}, failed_since={}, max_down_time={}, run_after={},\
check_frequency={}, check_timeout{})>'.format(
                        self.url,
                        self.expression,
                        self.current_hash,
                        self.capture_groups,
                        self.failed_since,
                        self.max_down_time,
                        self.run_after,
                        self.check_frequency,
                        self.check_timeout)

    MD5Check.__table__
    Table('md5s', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('current_hash', String()),
            Column('old_hash', String()),
            Column('failed_since', Integer()),
            Column('max_down_time', Integer()),
            Column('run_after', Integer()),
            Column('check_frequency', Integer()),
            Column('check_timeout', Integer()),   schema=None)

    StringCheck.__table__
    Table('strings', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('string_to_match', String()),
            Column('present', Integer()),
            Column('failed_since', Integer()),
            Column('max_down_time', Integer()),
            Column('run_after', Integer()),
            Column('check_frequency', Integer()),
            Column('check_timeout', Integer()),   schema=None)

    DiffCheck.__table__
    Table('diffs', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('current_content', String()),
            Column('failed_since', Integer()),
            Column('max_down_time', Integer()),
            Column('run_after', Integer()),
            Column('check_frequency', Integer()),
            Column('check_timeout', Integer()),   schema=None)

    RawCheck.__table__
    Table('raws', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('expression', String()),
            Column('current_hash', String()),
            Column('capture_groups', String()),
            Column('failed_since', Integer()),
            Column('max_down_time', Integer()),
            Column('run_after', Integer()),
            Column('check_frequency', Integer()),
            Column('check_timeout', Integer()),   schema=None)

    try:
        metadata.create_all(engine)
    except sqlalchemy.exc.OperationalError:
        print('Could not create or connect to database at {}'.format(
                                                    args.database_location))
        exit(1)

    Session = sessionmaker(bind=engine)
    session = Session()

    if args.check:
        run_checks()
    elif args.list:
        list_checks()
    elif args.add:
        if args.add[0] == 'md5':
            if len(args.add) != 2:
                print('call as -a \'md5\' \'url-to-check\'')
                exit(1)

            print(add_md5(args.add[1], args.max_down_time, args.check_frequency,
                        args.check_timeout))
        elif args.add[0] == 'string':
            if len(args.add) != 3:
                print('call as -a \'string\' string-to-check \'url-to-check\'')
                exit(1)

            print(add_string(args.add[2], args.add[1], args.max_down_time,
                    args.check_frequency, args.check_timeout))
        elif args.add[0] == 'diff':
            if len(args.add) != 2:
                print('call as -a \'diff\' \'url-to-check\'')
                exit(1)

            print(add_diff(args.add[1], args.max_down_time,
                    args.check_frequency, args.check_timeout))
        elif args.add[0] == 'raw':
            if len(args.add) != 3:
                print('call as -a \'raw\' \'expression\' \'url-to-check\'')
                exit(1)

            print(add_raw(args.add[2], args.add[1], args.max_down_time,
                    args.check_frequency, args.check_timeout))
        else:
            print('Choose either md5, string, diff or raw.')

    elif args.delete:
        if len(args.delete) != 2:
            print('call as -d \'check_type\' \'url-to-remove\'')
            exit(1)

        print(delete_check(args.delete[0], args.delete[1]))
    elif args.import_file:
        error = import_from_file(args.import_file)
        if error:
            print(error)
            exit(1)
    else:
        print("""\
Arguments:
  -h/--help\t\tShow the help message and exit
  -c/--check\t\tRun checks against all monitored urls
  -l/--list\t\tList stored checks from the database
  -a/--add\t\tAdds a check to the database:
  \t\t\t\t-a md5 [url]
  \t\t\t\t-a string [string] [url]
  \t\t\t\t-a diff [url]
  \t\t\t\t-a raw [expression] [url]
  -d/--delete\t\tDelete a check:
  \t\t\t\t-d [check_type] [url]
  --max-down-time\t\tNumber of seconds a site can be down for before warning
  --check-frequency\tNumber of seconds to wait between checks
  --check-timeout\t\tNumber of seconds to check_timeout after
  --database-location\tSpecify a database name and location
  --import-file\t\tSpecify a file to populate the database from\
  """)
