import mysql.connector

mydb = mysql.connector.connect(
    host="localhost",
    user="root",
    password="password@2005",
    auth_plugin='mysql_native_password'
)

mycursor = mydb.cursor()

mycursor.execute("DROP DATABASE IF EXISTS my_hospital")
mycursor.execute("CREATE DATABASE my_hospital")

mycursor.execute("SHOW DATABASES")

for db in mycursor:
    print(db)

