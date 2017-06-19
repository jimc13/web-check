# How do I give a relative path to the virtual enviroment
import argparse
import requests
import html2text
import hashlib
import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Table, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

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
    if check.failed_connections:
        print('Reastablished connection to {} after {} failed \
connections'.format(check.url, check.failed_connections))
        check.failed_connections = 0
        session.commit()

# check will be run from a cron so should warn/log on errors depending on
# serverity, the rest of the functions should just error out and give the user
# an explanation
def run_checks():
    '''Perform hash, string and difference checks for all stored url's'''
    # The frequency field is currently being ignored whilst I get everything
    # else working
    Session = sessionmaker(bind=engine)
    session = Session()
    for check in session.query(MD5Check).order_by(MD5Check.id):
        try:
            url_content = requests.get(check.url)
        except requests.exceptions.ConnectionError:
            failed_connection(check, session)
            continue

        if url_content.status_code != 200:
            failed_connection(check, session)
            continue

        check_if_failed(check, session)
        new_hash = get_md5(url_content.text)
        if new_hash == check.current_hash:
            continue

        if new_hash == check.old_hash:
            print('The md5 for {} has been reverted'.format(check.url))
        else:
            print('The md5 for {} has changed'.format(check.url))

        check.old_hash = check.current_hash
        check.current_hash = new_hash
        session.commit()

    for check in session.query(StringCheck).order_by(StringCheck.id):
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
                session.commit()
            else:
                print('{} is now present on {}'.format(check.string_to_match,
                                                    check.url))
                check.present = 1
                session.commit()

    return ''

def md5(url, error_warn, frequency):
    '''
    Add a database entry for a url to monitor the md5 hash of.  Returns message
    relating to success

    (I've realised this is going to give incorrect error codes).
    '''
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

    current_hash = get_md5(url_content.text)
    Session = sessionmaker(bind=engine)
    session = Session()
    check = MD5Check(url=url, current_hash=current_hash, failed_connections=0,
                max_failed_connections=error_warn, check_frequency=frequency)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        return 'Already in database'
    return 'Added MD5 Check for {}'.format(url)

def string(url, string, error_warn, frequency):
    '''Add a database entry for a url to monitor for a string'''
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

    if string_exists:
        print('{} is currently present, will alert if this changes'.format(
                                                                string))
    else:
        print('{} is currently not present, will alert if this changes'.format(
                                                                    string))

    Session = sessionmaker(bind=engine)
    session = Session()
    check = StringCheck(url=url, string_to_match=string, present=string_exists,
                    failed_connections=0, max_failed_connections=error_warn,
                    check_frequency=frequency)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        return 'Already in database'
    return 'Added String Check for {}'.format(url)

def diff(url, error_warn, frequence):
    '''Add a database entry for a url to monitor for any changes'''
    return (url, string, error_warn, frequency, database)

def list_checks(verbose=False):
    """
    The format needs a full review
    I intend to scrap verbose mode and just print the entire table in the
    same format as SELECT * FROM table would do
    """
    # not sure if I want this printing out or passing lists or json back as a
    # return
    Session = sessionmaker(bind=engine)
    session = Session()
    print('MD5 Checks:')
    if verbose:
        # I would like to change the formatting of the over to match that of
        # SELECT * FROM tables
        print('| {: ^77}|\n|{: ^39}|{: ^38}|\n|{: ^25}|{: ^26}|{: ^25}|\n\
|{: ^78}|'.format('URL', 'Current Hash', 'Previous Hash', 'Failed Connections',
            'Warn After', 'Delay Between Checks', ''))
        for check in session.query(MD5Check).order_by(MD5Check.id):
            print('| {: ^77}|\n|{: ^39}|{: ^38}|\n|{: ^25}|{: ^26}|{: ^25}|\n\
|{: ^78}|'.format(str(check.url), str(check.current_hash), str(check.old_hash),
            str(check.failed_connections), str(check.max_failed_connections),
            str(check.check_frequency), ''))
            #print(check.url, check.current_hash, check.old_hash,
            # check.failed_connections, check.max_failed_connections,
            # check.check_frequency)
    else:
        print('| {: <50}|{: ^8}|{: ^8}|{: ^8}|'.format('URL', 'Failed', 'Warn',
                                                    'Delay'))
        for check in session.query(MD5Check).order_by(MD5Check.id):
            # '{}'.format(None) is fine BUT '{: ^10}'.format(None) is not,
            # this makes no-sence to me, converting everything to a string is
            # the workarround I have gone for
            print('| {: <50}|{: ^8}|{: ^8}|{: ^8}|'.format(
                                            str(check.url),
                                            str(check.failed_connections),
                                            str(check.max_failed_connections),
                                            str(check.check_frequency)))

    print('String Checks:')
    print('| {: <32}|{: ^8}|{: ^8}|{: ^8}|{: ^8}|{: ^8}|'.format('URL',
                            'String', 'Present', 'Failed', 'Warn', 'Delay'))
    for check in session.query(StringCheck).order_by(StringCheck.id):
        # '{}'.format(None) is fine BUT '{: ^10}'.format(None) is not,
        # this makes no-sence to me, converting everything to a string is
        # the workarround I have gone for
        print('| {: <32}|{: ^8}|{: ^8}|{: ^8}|{: ^8}|{: ^8}|'.format(
                                        str(check.url),
                                        str(check.string_to_match),
                                        str(check.present),
                                        str(check.failed_connections),
                                        str(check.max_failed_connections),
                                        str(check.check_frequency)))

    return ''

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--check', action='store_true',
        help='Run checks against all monitored urls')
    parser.add_argument('-l', '--list', action='store_true',
        help='Maximum number of set string that can occur')
    parser.add_argument('-d', '--delete',
        help='The entry to delete id must be used')
    parser.add_argument('-a', '--add', nargs='+',
        help='The type of check to setup and what url to check against')
    parser.add_argument('--warn-after', default=24,
        help='Number of failed network attempts to warn after')
    parser.add_argument('--check-frequency', default=3600,
        help='Specify the number of seconds to check after')
    parser.add_argument('--database-location', default='checks.db',
        help='Specify a database name and location')
    parser.add_argument('-v', '--verbose', action='store_true',
        help='Enables verbose mode')
    args = parser.parse_args()

    engine = create_engine('sqlite:///{}'.format(args.database_location))
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
        check_frequency = Column(Integer)
        def __repr__(self):
            return '<url(url={}, current_hash={}, old_hash={},\
failed_connections={}, max_failed_connections={}, check_frequency={})>'.format(
                            self.url, self.current_hash, self.old_hash,
                            self.failed_connections,
                            self.max_failed_connections,
                            self.check_frequency)

    class StringCheck(Base):
        __tablename__ = 'strings'
        id = Column(Integer, primary_key=True)
        url = Column(String)
        string_to_match = Column(String)
        present = Column(Integer)
        failed_connections = Column(Integer)
        max_failed_connections = Column(Integer)
        check_frequency = Column(Integer)
        def __repr__(self):
            return '<url(url={}, string_to_match={}, should_exist={},\
failed_connections={}, max_failed_connections={}, check_frequency={})>'.format(
                            self.url, self.string_to_match, self.should_exist,
                            self.failed_connections,
                            self.max_failed_connections,
                            self.check_frequency)

    class DiffCheck(Base):
        __tablename__ = 'diffs'
        id = Column(Integer, primary_key=True)
        url = Column(String)
        current_content = Column(String)
        failed_connections = Column(Integer)
        max_failed_connections = Column(Integer)
        check_frequency = Column(Integer)
        def __repr__(self):
            return '<url(url={}, current_content={}, failed_connections=\
{}, max_failed_connections={}, check_frequency={})>'.format(
                            self.url, self.string_to_match,
                            self.failed_connections,
                            self.max_failed_connections,
                            self.check_frequency)

    MD5Check.__table__
    Table('md5s', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('current_hash', String()),
            Column('old_hash', String()),
            Column('failed_connections', Integer()),
            Column('max_failed_connections', Integer()),
            Column('check_frequency', Integer()),   schema=None)

    StringCheck.__table__
    Table('strings', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('string_to_match', String()),
            Column('present', Integer()),
            Column('failed_connections', Integer()),
            Column('max_failed_connections', Integer()),
            Column('check_frequency', Integer()),   schema=None)

    DiffCheck.__table__
    Table('diffs', metadata,
            Column('id', Integer(), primary_key=True, nullable=False),
            Column('url', String(), unique=True),
            Column('current_content', String()),
            Column('failed_connections', Integer()),
            Column('max_failed_connections', Integer()),
            Column('check_frequency', Integer()),   schema=None)

    metadata.create_all(engine)

    """
    Session = sessionmaker(bind=engine)
    session = Session()
    check = MD5Check(url='https://google.com', max_failed_connections='24',
                check_frequency='60')
    session.add(check)
    try:
        session.commit()
    except:
        print('Already in database')

    #print(MD5Check.__table__.constraints)
    #a = session.query(MD5Check)
    #print('\n',a.all(),'\n')
    #print('\n',a.one().url,'\n')
    """

    if args.check:
        run_checks()
    elif args.add:
        if args.add[0] == 'md5':
            if len(args.add) != 2:
                print('call as -a md5 url-to-check')
                exit(1)
            try:
                print(md5(args.add[1], args.warn_after, args.check_frequency))
            except:
                print('Exiting due to md5 error')
                raise
                #exit(1)
        elif args.add[0] == 'string':
            if len(args.add) != 3:
                print('call as -a string string-to-check url-to-check')
                exit(1)
            print(string(args.add[2], args.add[1], args.warn_after,
                args.check_frequency))
        elif args.add[0] == 'diff':
            if len(args.add) != 2:
                print('call as -a diff url-to-check')
                exit(1)
            print(diff(args.add[1], args.warn_after, args.check_frequency))
        else:
            print('Choose either md5, string or diff.')
    elif args.list:
        list_checks(args.verbose)
    elif args.delete:
        print('delete')
    else:
        print('''
-c --check\t\tRun checks against all monitored urls
-l --list\t\tList stored checks from the database
-a --add\t\tAdds a check in the database\n\t\t\t\tRequires md5/string/diff url
--warn-after\t\tNumber of failed network attempts to warn after
--check-frequency\tSpecify the number of seconds to check after
--database-location\tSpecify a database name and location
-v --verbose\t\tEnables verbose mode, currently only used for list
''')
