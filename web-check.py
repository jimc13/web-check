# How do I give a relative path to the virtual enviroment
import argparse
import requests
import hashlib
import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Table, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# check will be run from a cron so should warn/log on errors depending on serverity, the rest of the functions should just error out and give the user an explanation
def check():
    '''Perform hash, string and difference checks for all stored url's'''
# The frequency field is currently being ignored whilst I get everything else working
    for check in session.query(MD5Check).order_by(MD5Check.id):
        try:
            url_content = requests.get(check.url)
        except requests.exceptions.ConnectionError:
            check.failed_connections += 1

        if url_content.status_code != 200:
            check.failed_connections += 1

        check.current_hash
        new_hash = hashlib.md5(url_content.content).hexdigest()
        if new_hash == current_hash:
            continue

        if new_hash == check.old_hash:
            print('Changes to {} were reverted'.format(check.url))
        else:
            print('{} has changed'.format(check.url))

        check.old_hash = check.current_hash
        check.current_hash = new_hash

    return ''

def md5(url, error_warn, frequency):
    '''Add a database entry for a url to monitor the md5 hash of.  Returns message relating to success (I've realised this is going to give incorrect error codes).'''
    try:
        url_content = requests.get(url)
    except requests.exceptions.ConnectionError:
        return 'Could not connect to chosen url'
    except requests.exceptions.MissingSchema as e:
        return e

    if url_content.status_code != 200:
        return '{} code from server'.format(url_content.status_code)

    current_hash = hashlib.md5(url_content.content).hexdigest()

    Session = sessionmaker(bind=engine)
    session = Session()
    check = MD5Check(url=url, current_hash=current_hash, max_failed_connections=error_warn, check_frequency=frequency)
    session.add(check)
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        return 'Already in database'
    return 'Added MD5 Check for {}'.format(url)

def string(url, string, error_warn, frequency):
    '''Add a database entry for a url to monitor for a string'''
    return (url, string, error_warn, frequency, database)

def diff(url, error_warn, frequence):
    '''Add a database entry for a url to monitor for any changes'''
    return (url, string, error_warn, frequency, database)

def list_checks(verbose=False):
    # not sure if I want this printing out or passing lists or json back as a return
    Session = sessionmaker(bind=engine)
    session = Session()
    print('MD5 Checks:')
    if verbose:
        print('|{: ^78}|\n|{: ^39}|{: ^38}|\n|{: ^25}|{: ^26}|{: ^25}|\n|{: ^78}|'.format('URL', 'Current Hash', 'Previous Hash', 'Failed Connections', 'Warn After', 'Delay Between Checks', ''))
        for check in session.query(MD5Check).order_by(MD5Check.id):
            print('|{: ^78}|\n|{: ^39}|{: ^38}|\n|{: ^25}|{: ^26}|{: ^25}|\n|{: ^78}|'.format(str(check.url), str(check.current_hash), str(check.old_hash), str(check.failed_connections), str(check.max_failed_connections), str(check.check_frequency), ''))
            #print(check.url, check.current_hash, check.old_hash, check.failed_connections, check.max_failed_connections, check.check_frequency)
    else:
        print('|{: <51}|{: ^8}|{: ^8}|{: ^8}|'.format('URL', 'Failed', 'Warn', 'Delay'))
        for check in session.query(MD5Check).order_by(MD5Check.id):
            # '{}'.format(None) is fine BUT '{: ^10}'.format(None) is not, this makes no-sence to me, converting everything to a string is the workarround I have gone for
            print('|{: <51}|{: ^8}|{: ^8}|{: ^8}|'.format(str(check.url), str(check.failed_connections), str(check.max_failed_connections), str(check.check_frequency)))

    return ''

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--check', action='store_true', help='Run checks against all monitored urls')
    parser.add_argument('-l', '--list', action='store_true', help='Maximum number of set string that can occur')
    parser.add_argument('-d', '--delete', help='The entry to delete id must be used')
    parser.add_argument('-a', '--add', nargs='+', help='The type of check to setup and what url to check against')
    parser.add_argument('--warn-after', default=24, help='Number of failed network attempts to warn after')
    parser.add_argument('--check-frequency', default=3600, help='Specify the number of seconds to check after')
    parser.add_argument('--database-location', default='checks.db', help='Specify a database name and location')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enables verbose mode')
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
            return '<url(url={}, current_hash={}, old_hash={}, failed_connections=\
                    {}, max_failed_connections={}, check_frequency={})>'.format(
                                self.url, self.current_hash, self.old_hash,
                                self.failed_connections,
                                self.max_failed_connections,
                                self.check_frequency)

    class StringCheck(Base):
        __tablename__ = 'strings'
        id = Column(Integer, primary_key=True)
        url = Column(String)
        string_to_match = Column(String)
        should_exist = Column(Integer)
        failed_connections = Column(Integer)
        max_failed_connections = Column(Integer)
        check_frequency = Column(Integer)
        def __repr__(self):
            return '<url(url={}, string_to_match={}, should_exist={}, failed_connections=\
                    {}, max_failed_connections={}, check_frequency={})>'.format(
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

    metadata.create_all(engine)

    """
    Session = sessionmaker(bind=engine)
    session = Session()
    check = MD5Check(url='https://google.com', max_failed_connections='24', check_frequency='60')
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
        check()
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
            print(string(args.add[2], args.add[1], args.warn_after, args.check_frequency))
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
        print('There is no interactive mode, choose some command line arguments.')
