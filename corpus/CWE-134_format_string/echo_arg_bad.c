#include <stdio.h>

int echo_arg_bad(int argc, char **argv) {
    /* argv[1] is a format string here */
    if (argc > 1) printf(argv[1]);
    return 0;
}
