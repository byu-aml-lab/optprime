from __future__ import division
from . import _general

try:
    range = xrange
except NameError:
    pass


class NegBinomial(_general._Base):
    def dims(self, r=6, p=0.3):
        self.r = r
        self.p = p
        self.q = 1 - p

        self.constraints = ((0,1000L),)

    def __call__(self, x):
        x, = x
        fac = self.choose( x + self.r - 1, self.r - 1 )
        return fac * (self.p ** self.r) * (self.q ** x)

    @staticmethod
    def choose( n, k ):
        """Compute n! / (k! * (n-k)!)"""
        # In order to keep things neat, we don't fully compute the n! portion
        # of the equation, since the larger of k! and (n-k)! will cancel out
        # the tail end of the calculation.

        # This won't change the outcome
        n = long(n)
        k = long(k)
        k = max(n-k, k)

        if k == n:
            return 1L

        # Generate n! / k!
        numerator = long(n)
        for i in range(k+1,n):
            numerator *= i

        # Generate (n-k)!
        denominator = long(n-k)
        for i in range(2,n-k):
            denominator *= i

        return numerator // denominator

