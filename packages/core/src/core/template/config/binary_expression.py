"""Binary expression operator mappings."""

BinaryExpressionOperatorMap: dict[str, str] = {
    "<operator>.addition": "+",
    "<operator>.subtraction": "-",
    "<operator>.multiplication": "*",
    "<operator>.division": "/",
    "<operator>.modulo": "%",
    "<operator>.shiftLeft": "<<",
    "<operator>.arithmeticShiftRight": ">>",
    "<operator>.and": "&",
    "<operator>.or": "|",
    "<operator>.xor": "^",
    "<operator>.logicalAnd": "&&",
    "<operator>.logicalOr": "||",
    "<operator>.equals": "==",
    "<operator>.notEquals": "!=",
    "<operator>.lessThan": "<",
    "<operator>.lessEqualsThan": "<=",
    "<operator>.greaterThan": ">",
    "<operator>.greaterEqualsThan": ">=",
    "<operator>.assignmentPlus": "+=",
    "<operator>.assignmentMinus": "-=",
    "<operator>.assignmentMultiplication": "*=",
    "<operator>.assignmentDivision": "/=",
    "<operator>.pointerCall": "()",
    "<operator>.conditional": "?:",
    "<operator>.op_ellipses": "...",
}

BinaryExpressionBooleanMap: dict[str, str] = {
    "<operator>.equals": "boolean",
    "<operator>.notEquals": "boolean",
    "<operator>.lessThan": "boolean",
    "<operator>.lessEqualsThan": "boolean",
    "<operator>.greaterThan": "boolean",
    "<operator>.greaterEqualsThan": "boolean",
    "<operator>.logicalAnd": "boolean",
    "<operator>.logicalOr": "boolean",
}


