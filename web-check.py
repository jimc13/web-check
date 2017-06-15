# How do I give a relative path to the virtual enviroment
import argparse
import requests
import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

engine = create_engine('sqlite:///checks.db', echo=True)
Base = declarative_base()
class MD5Check(Base):
    __tablename__ = 'md5s'
    id = Column(Integer, primary_key=True)
    url = Column(String)
    current_hash = Column(String)
    old_hash = Column(String)
    failed_connections = Column(Integer)
    max_failed_connections = Column(Integer)
    check_frequency = Column(Integer)
    def __repr__(self):
        return "<url(url={}, current_hash={}, old_hash={}, failed_connections=\
                {}, max_failed_connections={}, check_frequency={})>".format(
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
        return "<url(url={}, string_to_match={}, should_exist={}, failed_connections=\
                {}, max_failed_connections={}, check_frequency={})>".format(
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
        return "<url(url={}, current_content={}, failed_connections=\
                {}, max_failed_connections={}, check_frequency={})>".format(
                            self.url, self.string_to_match,
                            self.failed_connections,
                            self.max_failed_connections,
                            self.check_frequency)
MD5Check.__table__
Table('users', MetaData(bind=None),
            Column('id', Integer(), table=<users>, primary_key=True, nullable=False),
            Column('name', String(), table=<users>),
            Column('fullname', String(), table=<users>),
            Column('password', String(), table=<users>), schema=None)

Session = sessionmaker(bind=engine)
session = Session()
check = MD5Check(url='https://google.com', max_failed_connections='24', check_frequency='60')
session.add(check)
print(check.url)
print(check.failed_connections)
session.commit()



# check will be run from a cron so should warn/log on errors depending on serverity, the rest of the functions should just error out and give the user an explanation
def check(database):
    """Perform hash, string and difference checks for all stored url's"""
    return database

def md5(url, error_warn, frequency, database):
    """Add a database entry for a url to monitor the md5 hash of"""
    try:
        url_content = requests.get(url)
    except requests.exceptions.ConnectionError:
        print('Could not connect to chosen url')
        raise
    if url_content.status_code != 200:
        print('{} code from server'.format(url_content.status_code))
        exit(1)
    return ''

def string(url, string, error_warn, frequency, database):
    """Add a database entry for a url to monitor for a string"""
    return (url, string, error_warn, frequency, database)

def diff(url, error_warn, frequency, database):
    """Add a database entry for a url to monitor for any changes"""
    return (url, string, error_warn, frequency, database)

def list_checks(database, verbose=False):
    # not sure if I want this printing out or passing lists or json back as a return
    return ''

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--check', action='store_true', help='Run checks against all monitored urls')
    parser.add_argument('-l', '--list', action='store_true', help='Maximum number of set string that can occur')
    parser.add_argument('-d', '--delete', help='The entry to delete id must be used')
    parser.add_argument('-a', '--add', nargs='+', help='The type of check to setup and what url to check against')
    parser.add_argument('--warn-after', default=24, help='Number of failed network attempts to warn after')
    parser.add_argument('--check-frequency', default=3600, help='Specify the number of seconds to check after')
    parser.add_argument('--database-location', default='web-check.db', help='Specify a database name and location')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enables verbose mode')
    args = parser.parse_args()

    if args.check:
        print(check(args.database_location))
    elif args.add:
        if args.add[0] == 'md5':
            if len(args.add) != 2:
                print('call as -a md5 url-to-check')
                exit(1)
            try:
                print(md5(args.add[1], args.warn_after, args.check_frequency, args.database_location))
            except:
                print('Exiting due to md5 error')
                raise
                #exit(1)
        elif args.add[0] == 'string':
            if len(args.add) != 3:
                print('call as -a string string-to-check url-to-check')
                exit(1)
            print(string(args.add[2], args.add[1], args.warn_after, args.check_frequency, args.database_location))
        elif args.add[0] == 'diff':
            if len(args.add) != 2:
                print('call as -a diff url-to-check')
                exit(1)
            print(diff(args.add[1], args.warn_after, args.check_frequency, args.database_location))
        else:
            print('Choose either md5, string or diff.')
    elif args.list:
        list_checks(args.database_location, args.verbose)
    elif args.delete:
        print('delete')
    else:
        print('There is no interactive mode, choose some command line arguments.')
