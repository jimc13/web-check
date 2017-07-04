#!/usr/bin/env python3
try:
    import sys
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
    Input html bytes.  Returns utf-8 markdown without links

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
    Input html bytes. Returns MD5 hash.
    """
    return hashlib.md5(get_text(html).encode('utf-8')).hexdigest()

def failed_connection(check, session):
    # According to the internet this generates the correct SQL and
    # prevents race conditions caused by +=
    check.failed_connections = check.failed_connections + 1
    if check.failed_connections - 1 == check.max_failed_connections:
        print('{} failed connections to {} limmit was set at {}'.format(
                                                check.failed_connections,
                                                check.url,
                                                check.max_failed_connections))
    session.commit()

# This should not alert if the failed connections was within the warning
# limmit - no initial message has been sent
def check_if_failed(check, session):
    if check.failed_connections >= check.max_failed_connections:
        print('Reastablished connection to {} after {} failed \
connections'.format(check.url, check.failed_connections))
        check.failed_connections = 0
        session.commit()

# check will be run from a cron so should warn/log on errors depending on
# serverity, the rest of the functions should just error out and give the user
# an explanation
def run_checks():
    """Perform hash, string and difference checks for all stored url's"""
    # The frequency field is currently being ignored whilst I get everything
    # else working
    for check in session.query(MD5Check).filter(MD5Check.next_run <
                    time.time()).order_by(MD5Check.id):
        try:
            url_content = requests.get(check.url)
        except requests.exceptions.ConnectionError:
            failed_connection(check, session)
            continue

        if url_content.status_code != 200:
            failed_connection(check, session)
            continue

        check_if_failed(check, session)
        try:
            new_hash = get_md5(url_content.text)
        except:
            print('Failed to hash response from {}'.format(check.url))
            continue

        if new_hash != check.current_hash:
            if new_hash == check.old_hash:
                print('The md5 for {} has been reverted'.format(check.url))
            else:
                print('The md5 for {} has changed'.format(check.url))

            check.old_hash = check.current_hash
            check.current_hash = new_hash

        check.next_run = time.time() + check.check_frequency
        session.commit()

    for check in session.query(StringCheck).filter(StringCheck.next_run <
                    time.time()).order_by(StringCheck.id):
        try:
            url_content = requests.get(check.url)
        except requests.exceptions.ConnectionError:
            failed_connection(check, session)
            continue

        if url_content.status_code != 200:
            failed_connection(check, session)
            continue

        check_if_failed(check, session)
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

        check.next_run = time.time() + check.check_frequency
        session.commit()

    for check in session.query(DiffCheck).filter(DiffCheck.next_run <
                    time.time()).order_by(DiffCheck.id):
        try:
            url_content = requests.get(check.url)
        except requests.exceptions.ConnectionError:
            failed_connection(check, session)
            continue

        if url_content.status_code != 200:
            failed_connection(check, session)
            continue

        check_if_failed(check, session)
        text = get_text(url_content.text)
        if text != check.current_content:
            # I'm not happy with this as the output format but I'm going to
            # focus on something else
            for line in difflib.context_diff(check.current_content.split('\n'),
                            text.split('\n'),
                            fromfile='Stored content for {}'.format(check.url),
                            tofile='New content for {}'.format(check.url)):
                print(line)
            check.current_content = text

        check.next_run = time.time() + check.check_frequency
        session.commit()
    return ''

def md5(url, error_warn, frequency):
    """
    Add a database entry for a url to monitor the md5 hash of.  Returns message
    relating to success

    (I've realised this is going to give incorrect error codes).
    """
    try:
        url_content = requests.get(url)
    except requests.exceptions.ConnectionError:
        return 'Could not connect to chosen url'
    except requests.exceptions.MissingSchema as e:
        return e
    except requests.exceptions.InvalidSchema as e:
        return e

    if url_content.status_code != 200:
        return '{} code from server'.format(url_content.status_code)

    try:
        current_hash = get_md5(url_content.text)
    except:
        return 'Failed to hash response from {}'.format(url)
    check = MD5Check(url=url,
                current_hash=current_hash,
                failed_connections=0,
                max_failed_connections=error_warn,
                next_run=0,
                check_frequency=frequency)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        return 'An entry for {} is already in database'.format(url)
    else:
        return 'Added MD5 Check for {}'.format(url)

def string(url, string, error_warn, frequency):
    """Add a database entry for a url to monitor for a string"""
    try:
        url_content = requests.get(url)
    except requests.exceptions.ConnectionError:
        return 'Could not connect to chosen url'
    except requests.exceptions.MissingSchema as e:
        return e
    except requests.exceptions.InvalidSchema as e:
        return e

    if url_content.status_code != 200:
        return '{} code from server'.format(url_content.status_code)

    string_exists = 0
    if string in get_text(url_content.text):
        string_exists = 1

    check = StringCheck(url=url,
                    string_to_match=string,
                    present=string_exists,
                    failed_connections=0,
                    max_failed_connections=error_warn,
                    next_run= 0,
                    check_frequency=frequency)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        return 'An entry for {} is already in database'.format(url)
    else:
        if string_exists:
            print('{} is currently present, will alert if this changes'.format(
                                                                    string))
        else:
            print('{} is currently not present, will alert if this changes'
.format(string))

        return 'Added String Check for {}'.format(url)

def diff(url, error_warn, frequency):
    """Add a database entry for a url to monitor for any text changes"""
    try:
        url_content = requests.get(url)
    except requests.exceptions.ConnectionError:
        return 'Could not connect to chosen url'
    except requests.exceptions.MissingSchema as e:
        return e
    except requests.exceptions.InvalidSchema as e:
        return e

    if url_content.status_code != 200:
        return '{} code from server'.format(url_content.status_code)

    check = DiffCheck(url=url,
                    current_content=get_text(url_content.text),
                    failed_connections=0,
                    max_failed_connections=error_warn,
                    next_run=0,
                    check_frequency=frequency)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        return 'An entry for {} is already in database'.format(url)
    else:
        return 'Added Diff Check for {}'.format(url)


    return (url, string, error_warn, frequency, database)

def get_longest_md5():
    longest_url = 3
    longest_current_hash = 12
    longest_old_hash = 8
    longest_failed_connections = 18
    longest_max_failed_connections = 22
    longest_next_run = 8
    longest_check_frequency = 15
    for check in session.query(MD5Check).order_by(MD5Check.id):
        if len(str(check.url)) > longest_url:
            longest_url = len(str(check.url))
        if len(str(check.current_hash)) > longest_current_hash:
            longest_current_hash = len(str(check.current_hash))
        if len(str(check.old_hash)) > longest_old_hash:
            longest_old_hash = len(str(check.old_hash))
        if len(str(check.failed_connections)) > longest_failed_connections:
            longest_failed_connections = len(str(check.failed_connections))
        if len(str(check.max_failed_connections)) > \
                                longest_max_failed_connections:
            longest_max_failed_connections =\
                                    len(str(check.max_failed_connections))
        if len(str(check.next_run)) > longest_next_run:
            longest_next_run = len(str(check.next_run))
        if len(str(check.check_frequency)) > longest_check_frequency:
            longest_check_frequency = len(str(check.check_frequency))

    return (('url', longest_url),
        ('current_hash', longest_current_hash),
        ('old_hash', longest_old_hash),
        ('failed_connections', longest_failed_connections),
        ('max_failed_connections', longest_max_failed_connections),
        ('next_run', longest_next_run),
        ('check_frequency', longest_check_frequency))

def get_longest_string():
    longest_url = 3
    longest_string_to_match = 15
    longest_present = 7
    longest_failed_connections = 18
    longest_max_failed_connections = 22
    longest_next_run = 8
    longest_check_frequency = 15
    for check in session.query(StringCheck).order_by(StringCheck.id):
        if len(str(check.url)) > longest_url:
            longest_url = len(str(check.url))
        if len(str(check.string_to_match)) > longest_string_to_match:
            longest_string_to_match = len(str(check.string_to_match))
        if len(str(check.present)) > longest_present:
            longest_present = len(str(check.present))
        if len(str(check.failed_connections)) > longest_failed_connections:
            longest_failed_connections = len(str(check.failed_connections))
        if len(str(check.max_failed_connections)) > \
                                longest_max_failed_connections:
            longest_max_failed_connections =\
                                    len(str(check.max_failed_connections))
        if len(str(check.next_run)) > longest_next_run:
            longest_next_run = len(str(check.next_run))
        if len(str(check.check_frequency)) > longest_check_frequency:
            longest_check_frequency = len(str(check.check_frequency))

    return (('url', longest_url),
        ('string_to_match', longest_string_to_match),
        ('present', longest_present),
        ('failed_connections', longest_failed_connections),
        ('max_failed_connections', longest_max_failed_connections),
        ('next_run', longest_next_run),
        ('check_frequency', longest_check_frequency))

def get_longest_diff():
    longest_url = 3
    longest_current_content = 15
    longest_failed_connections = 18
    longest_max_failed_connections = 22
    longest_next_run = 8
    longest_check_frequency = 15
    for check in session.query(DiffCheck).order_by(DiffCheck.id):
        if len(str(check.url)) > longest_url:
            longest_url = len(str(check.url))
        # Not checking how long current_content is since it will be long and
        # make the table look silly
        #if len(str(check.current_content)) > longest_current_content:
        #    longest_current_content = len(str(check.current_content))
        if len(str(check.failed_connections)) > longest_failed_connections:
            longest_failed_connections = len(str(check.failed_connections))
        if len(str(check.max_failed_connections)) > \
                                longest_max_failed_connections:
            longest_max_failed_connections =\
                                    len(str(check.max_failed_connections))
        if len(str(check.next_run)) > longest_next_run:
            longest_next_run = len(str(check.next_run))
        if len(str(check.check_frequency)) > longest_check_frequency:
            longest_check_frequency = len(str(check.check_frequency))

    return (('url', longest_url),
        ('current_content', longest_current_content),
        ('failed_connections', longest_failed_connections),
        ('max_failed_connections', longest_max_failed_connections),
        ('next_run', longest_next_run),
        ('check_frequency', longest_check_frequency))

def list_checks():
    """
    The format needs a full review
    I intend to scrap verbose mode and just print the entire table in the
    same format as SELECT * FROM table would do
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
                        str(check.failed_connections),
                        str(check.max_failed_connections),
                        str(check.next_run),
                        str(check.check_frequency)))

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
                        str(check.failed_connections),
                        str(check.max_failed_connections),
                        str(check.next_run),
                        str(check.check_frequency)))

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
        # I couldn't work out how to implement class.variable so had to
        # write this out 3 times despite being close to having it as a function
        print(table_skel.format(str(check.url),
                            str(check.current_content),
                            str(check.failed_connections),
                            str(check.max_failed_connections),
                            str(check.next_run),
                            str(check.check_frequency)))

    return ''

def delete_check(check_type, url):
    if check_type == 'md5':
        check = session.query(MD5Check).filter(MD5Check.url == url)
    elif check_type == 'string':
        check = session.query(StringCheck).filter(StringCheck.url == url)
    elif check_type == 'diff':
        check = session.query(DiffCheck).filter(DiffCheck.url == url)
    else:
        return 'Chose either md5, string or diff check'

    if check.delete():
        session.commit()
        return '{} check for {} removed'.format(check_type, url)

    return 'There is no {} check for {}'.format(check_type, url)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--check', action='store_true',
        help='Run checks against all monitored urls')
    parser.add_argument('-l', '--list', action='store_true',
        help='Maximum number of set string that can occur')
    parser.add_argument('-d', '--delete', nargs='+',
        help='The entry to delete id must be used')
    parser.add_argument('-a', '--add', nargs='+',
        help='The type of check to setup and what url to check against')
    parser.add_argument('--warn-after', default=24,
        help='Number of failed network attempts to warn after')
    parser.add_argument('--check-frequency', default=3600,
        help='Specify the number of seconds to check after')
    parser.add_argument('--database-location', default='checks.db',
        help='Specify a database name and location')
    args = parser.parse_args()

    engine = sqlalchemy.create_engine('sqlite:///{}'.format(args.database_location))
    Base = declarative_base()
    metadata = MetaData()

    class MD5Check(Base):
        __tablename__ = 'md5s'
        id = Column(Integer, primary_key=True)
        url = Column(String, unique=True)
        current_hash = Column(String)
        old_hash = Column(String)
        failed_connections = Column(Integer)
        max_failed_connections = Column(Integer)
        next_run = Column(Integer)
        check_frequency = Column(Integer)
        def __repr__(self):
            return '<url(url={}, current_hash={}, old_hash={},\
failed_connections={}, max_failed_connections={}, next_run={},\
check_frequency={})>'.format(
                        self.url,
                        self.current_hash,
                        self.old_hash,
                        self.failed_connections,
                        self.max_failed_connections,
                        self.next_run,
                        self.check_frequency)

    class StringCheck(Base):
        __tablename__ = 'strings'
        id = Column(Integer, primary_key=True)
        url = Column(String)
        string_to_match = Column(String)
        present = Column(Integer)
        failed_connections = Column(Integer)
        max_failed_connections = Column(Integer)
        next_run = Column(Integer)
        check_frequency = Column(Integer)
        def __repr__(self):
            return '<url(url={}, string_to_match={}, should_exist={},\
failed_connections={}, max_failed_connections={}, next_run={},\
check_frequency={})>'.format(
                        self.url,
                        self.string_to_match,
                        self.should_exist,
                        self.failed_connections,
                        self.max_failed_connections,
                        self.next_run,
                        self.check_frequency)

    class DiffCheck(Base):
        __tablename__ = 'diffs'
        id = Column(Integer, primary_key=True)
        url = Column(String)
        current_content = Column(String)
        failed_connections = Column(Integer)
        max_failed_connections = Column(Integer)
        next_run = Column(Integer)
        check_frequency = Column(Integer)
        def __repr__(self):
            return '<url(url={}, current_content={}, failed_connections=\
{}, max_failed_connections={}, next_run={},\
check_frequency={})>'.format(
                            self.url,
                            self.string_to_match,
                            self.failed_connections,
                            self.max_failed_connections,
                            self.next_run,
                            self.check_frequency)

    MD5Check.__table__
    Table('md5s', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('current_hash', String()),
            Column('old_hash', String()),
            Column('failed_connections', Integer()),
            Column('max_failed_connections', Integer()),
            Column('next_run', Integer()),
            Column('check_frequency', Integer()),   schema=None)

    StringCheck.__table__
    Table('strings', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('string_to_match', String()),
            Column('present', Integer()),
            Column('failed_connections', Integer()),
            Column('max_failed_connections', Integer()),
            Column('next_run', Integer()),
            Column('check_frequency', Integer()),   schema=None)

    DiffCheck.__table__
    Table('diffs', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('current_content', String()),
            Column('failed_connections', Integer()),
            Column('max_failed_connections', Integer()),
            Column('next_run', Integer()),
            Column('check_frequency', Integer()),   schema=None)

    metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    if args.check:
        run_checks()
    elif args.list:
        # Listing the checks uses a lot more resources than it needs to
        # How often will you list the checks are resources important
        list_checks()
    elif args.add:
        if args.add[0] == 'md5':
            if len(args.add) != 2:
                print('call as -a \'md5\' \'url-to-check\'')
                exit(1)

            print(md5(args.add[1], args.warn_after, args.check_frequency))
        elif args.add[0] == 'string':
            if len(args.add) != 3:
                print('call as -a \'string\' string-to-check \'url-to-check\'')
                exit(1)

            print(string(args.add[2], args.add[1], args.warn_after,
                args.check_frequency))
        elif args.add[0] == 'diff':
            if len(args.add) != 2:
                print('call as -a \'diff\' \'url-to-check\'')
                exit(1)

            print(diff(args.add[1], args.warn_after, args.check_frequency))
        else:
            print('Choose either md5, string or diff.')

    elif args.delete:
        if len(args.delete) != 2:
            print('call as -d \'check_type\' \'url-to-remove\'')
            exit(1)

        print(delete_check(args.delete[0], args.delete[1]))
    else:
        print("""Usage:
    -c --check\t\tRun checks against all monitored urls
    -l --list\t\tList stored checks from the database
    -a --add\t\tAdds a check in the database\n\t\t\t\tRequires md5/string/diff\
 url
    -d --delete\t\tDelete a check by specifying check_type url
    --warn-after\t\tNumber of failed network attempts to warn after
    --check-frequency\tSpecify the number of seconds to check after\n\t\t\t\t\
Maybe I should call it check wavelength
    --database-location\tSpecify a database name and location""")
