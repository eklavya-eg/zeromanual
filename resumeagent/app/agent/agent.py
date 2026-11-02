from langgraph import Graph, Node, Edge

class Agent:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, I am {self.name}."