#include <stdio.h>

int echo_arg_bad(int argc, char **argv) {
    if (argc > 1) printf(argv[1]);
    return 0;
}
