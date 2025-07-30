from crewai.tools import tool

class CalculatorTool:
    @staticmethod
    @tool("Make a calculation")
    def calculate(self,operation: str) -> str:
        """
        Useful to perform any mathematical calculations,
        like sum,minus,multiplication,diviion,etc.
        The input to this tool should be a valid mathematical expression,
        such as '2+2', '200*7', '10/2', or '5000/2*10'
        """
        try:
            return eval(operation)
        except SyntaxError:
            return f"Error calculating '{operation}': Invalid syntax in mathematical expression."
        except ZeroDivisionError:
            return f"Error calculating '{operation}': Division by zero is not allowed."