#!/usr/bin/python3
import argparse
import sqlite3
import requests

# check will be run from a cron so should warn/log on errors depending on serverity, the rest of the functions should just error out and give the user an explanation
def check(database):
    """Perform hash, string and difference checks for all stored url's"""
    return(database)
    c.execute('UPDATE hashes SET failed_connections = failed_connections+1 WHERE url = ?', (url))

def md5(url, error_warn, frequency, database):
    """Add a database entry for a url to monitor the md5 hash of"""
    conn = sqlite3.connect(database)
    c = conn.cursor()
    try:
        c.execute('CREATE TABLE IF NOT EXISTS hashes (url TEXT, current_hash TEXT, previous_hash TEXT, failed_connections INTEGER, max_failed_connections INTEGER, check_frequency, INTEGER, CONSTRAINT unique_name UNIQUE (url))')
    except sqlite3.DatabaseError:
        print('Error connecting to database\nAre you sure the file is in the correct format')

    try:
        c.execute('INSERT INTO hashes (url, max_failed_connections, check_frequency) VALUES (?, ?, ?)',  (url, error_warn, frequency))
    except sqlite3.IntegrityError:
        print('Url\'s must be unique, either modify or delete your current check')
        raise

    try:
        url_content = requests.get(url)
    except requests.exceptions.ConnectionError:
        print('Could not connect to chosen url')
        raise
    if url_content.status_code != 200:
        print('{} code from server'.format(url_content.status_code))
        exit(1)
    md5 = "hsgfh"
    last_md5 = "fwoi"
    t = (url, md5, last_md5, error_warn, frequency, database)
    c.execute('UPDATE hashes SET current_hash = ?, previous_hash = ? WHERE url = ?', (md5, last_md5, url))
    conn.commit()

    return('')

def string(url, string, error_warn, frequency, database):
    """Add a database entry for a url to monitor for a string"""
    return(url, string, error_warn, frequency, database)

def diff(url, error_warn, frequency, database):
    """Add a database entry for a url to monitor for any changes"""
    return(url, string, error_warn, frequency, database)

def list_checks(database, verbose=False):
    # not sure if I want this printing out or passing lists or json back as a return
    conn = sqlite3.connect(database)
    c = conn.cursor()
    for table in ("hashes", "strings", "diffs"):
        print('The {} table has the following entries:'.format(table))
        try:
            # couldn't get ? working to insert the table
            c.execute('SELECT * FROM {}'.format(table))
        except sqlite3.OperationalError:
            print('()')
            continue
        check = c.fetchone()
        if verbose:
            while check:
                if table == "hashes":
                    print('URL: "{0}"\nIs stored with hash: {1}\nAnd previous hash: {2}\nYou will be alerted after {4} failed connections in a row of which there are currently {3}\nThe check is run every {5} seconds\n'.format(check[0], check[1], check[2], check[3], check[4], check[5]))
                else:
                    print('NEEDS DOING')
                check = c.fetchone()
        else:
            while check:
                print(check)
                check = c.fetchone()

    return('')

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
