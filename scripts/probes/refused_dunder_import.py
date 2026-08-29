# MUST BE REFUSED
"""The other dynamic spelling, which reads as a builtin call rather than as an import."""

package = __import__("exactly")

assert package
