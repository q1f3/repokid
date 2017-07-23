class UnknownPermissions(Exception):
    def __init__(self, message, unknown_permissions):
        super(UnknownPermissions, self).__init__(message)
        self.unknown_permissions = unknown_permissions
