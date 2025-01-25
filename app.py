from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/')
def hello():
    return jsonify({"message": "Welcome to Arya and the Sheep API!"})

if __name__ == '__main__':
    app.run(debug=True)
