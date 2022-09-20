from marshmallow import Schema, fields


class WordSchema(Schema):
    id = fields.Integer(required=False)
    key = fields.String(required=True)
    desc = fields.String(required=True)
    is_used = fields.Boolean(required=False)


class WordsListSchema(Schema):
    words = fields.Nested(WordSchema, many=True)
