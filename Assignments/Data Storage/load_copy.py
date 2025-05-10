import time
import psycopg2
import argparse
import csv
from io import StringIO

DBname = "postgres"
DBuser = "postgres"
DBpwd = "postgres"
TableName = 'CensusData'
Datafile = "filedoesnotexist"  # This will be overridden by argument
CreateDB = False  # Set by argument flag

def initialize():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--datafile", required=True)
    parser.add_argument("-c", "--createtable", action="store_true")
    args = parser.parse_args()

    global Datafile
    Datafile = args.datafile
    global CreateDB
    CreateDB = args.createtable

# Read the CSV file as a list of dictionaries
def readdata(fname):
    print(f"Reading from the file: {fname}")
    with open(fname, mode="r", encoding="utf-8") as fil:
        dr = csv.DictReader(fil)
        rowlist = []
        for row in dr:
            rowlist.append(row)
    return rowlist

# Create the database table
def createTable(conn):
    with conn.cursor() as cursor:
        cursor.execute(f"""
            DROP TABLE IF EXISTS {TableName};
            CREATE TABLE {TableName} (
                TractId             NUMERIC,
                State               TEXT,
                County              TEXT,
                TotalPop            INTEGER,
                Men                 INTEGER,
                Women               INTEGER,
                Hispanic            DECIMAL,
                White               DECIMAL,
                Black               DECIMAL,
                Native              DECIMAL,
                Asian               DECIMAL,
                Pacific             DECIMAL,
                VotingAgeCitizen    DECIMAL,
                Income              DECIMAL,
                IncomeErr           DECIMAL,
                IncomePerCap        DECIMAL,
                IncomePerCapErr     DECIMAL,
                Poverty             DECIMAL,
                ChildPoverty        DECIMAL,
                Professional        DECIMAL,
                Service             DECIMAL,
                Office              DECIMAL,
                Construction        DECIMAL,
                Production          DECIMAL,
                Drive               DECIMAL,
                Carpool             DECIMAL,
                Transit             DECIMAL,
                Walk                DECIMAL,
                OtherTransp         DECIMAL,
                WorkAtHome          DECIMAL,
                MeanCommute         DECIMAL,
                Employed            INTEGER,
                PrivateWork         DECIMAL,
                PublicWork          DECIMAL,
                SelfEmployed        DECIMAL,
                FamilyWork          DECIMAL,
                Unemployment        DECIMAL
         );
              ALTER TABLE {TableName} ADD PRIMARY KEY (TractId);
              CREATE INDEX idx_{TableName}_State ON {TableName}(State);
   """)
def load_copy(conn, rowlist):
    with conn.cursor() as cursor:
        print(f"Load {len(rowlist)} rows using COPY")
        start = time.perf_counter()

        csv_data = StringIO()
        for row in rowlist:
            for key in row:
                if row[key] == '':
                    row[key] = '0'
            row['County'] = row['County'].replace("'", "")

            line = '\t'.join([
                row['TractId'],
                row['State'],
                row['County'],
                row['TotalPop'],
                row['Men'],
                row['Women'],
                row['Hispanic'],
                row['White'],
                row['Black'],
                row['Native'],
                row['Asian'],
                row['Pacific'],
                row['VotingAgeCitizen'],
                row['Income'],
                row['IncomeErr'],
                row['IncomePerCap'],
                row['IncomePerCapErr'],
                row['Poverty'],
                row['ChildPoverty'],
                row['Professional'],
                row['Service'],
                row['Office'],
                row['Construction'],
                row['Production'],
                row['Drive'],
                row['Carpool'],
                row['Transit'],
                row['Walk'],
                row['OtherTransp'],
                row['WorkAtHome'],
                row['MeanCommute'],
                row['Employed'],
                row['PrivateWork'],
                row['PublicWork'],
                row['SelfEmployed'],
                row['FamilyWork'],
                row['Unemployment']
            ])
            csv_data.write(line + '\n')

        csv_data.seek(0) 
        cursor.copy_from(csv_data, TableName.lower(), sep='\t', null='0')
        conn.commit()

        elapsed = time.perf_counter() - start
        print(f"Finished loading all the data using Copy_From. Elapsed Time : {elapsed:0.4f} seconds")

# Connect to database
def dbconnect():
    connection = psycopg2.connect(
        host="localhost",
        database=DBname,
        user=DBuser,
        password=DBpwd,
    )
    return connection

def main():
    initialize()
    conn = dbconnect()
    rowlist = readdata(Datafile)

    if CreateDB:
        createTable(conn)

    load_copy(conn, rowlist)

if __name__ == "__main__":
    main()
