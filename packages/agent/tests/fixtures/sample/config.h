/*
 * Shared declarations for the sample tree.
 *
 * This tree belongs to the agent package and to nothing else. It exists so the
 * index tests have real multi-file C with a real call graph, and so an
 * inspection can be scored: every function below is labelled VULNERABLE or
 * SAFE in its own header comment.
 */
#ifndef CONFIG_H
#define CONFIG_H

#include <stddef.h>

/* A request parsed from an untrusted source. Both fields are attacker
 * controlled; nothing in this tree validates them on the way in. */
typedef struct {
    char *url;
    char *body;
    size_t body_len;
} Request;

char *read_param(const Request *req);
void log_line(const char *message);

#endif
