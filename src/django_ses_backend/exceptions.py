class SESClientError(Exception):
    pass


class SESRateLimitError(SESClientError):
    pass


class SESRetryableClientError(SESClientError):
    pass