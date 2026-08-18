#include <string.h>

char *split_key_bad(char *line) {
    /* strchr returns NULL when the separator is absent */
    char *eq = strchr(line, '=');
    *eq = 0;
    return eq + 1;
}
