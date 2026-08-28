#include "config.h"

#include <stdio.h>

/*
 * SAFE. Returns the caller's own field unchanged.
 *
 * Its note matters more than its body: it is analysed before the functions
 * that call it, so "returns an unvalidated attacker-controlled string" is what
 * reaches their context.
 */
char *read_param(const Request *req)
{
    return req->url;
}

/* SAFE. Format string is a literal. */
void log_line(const char *message)
{
    printf("%s\n", message);
}
