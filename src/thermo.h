#ifndef THERMO_H_
#define THERMO_H_

#include <stdbool.h>
#include <stdint.h>

/* Temperatures in tenths of a degree C */
#define T_SETPOINT  200   /* 20.0 C */
#define T_HYST       10   /*  1.0 C */
#define T_OVERTEMP  350   /* 35.0 C */
#define T_MIN      -400   /* below this: open/broken sensor */
#define T_MAX      1000

typedef enum { ST_IDLE, ST_HEATING, ST_LOCKOUT, ST_FAULT } thermo_state_t;

typedef struct {
	thermo_state_t state;
} thermo_t;

/* Advance the state machine one step. Returns the heater command. */
bool thermo_step(thermo_t *t, int16_t temp, bool sensor_ok, bool reset_btn);

#endif /* THERMO_H_ */
