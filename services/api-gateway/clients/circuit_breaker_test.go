package clients

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestCircuitBreaker_InitialState(t *testing.T) {
	cb := NewCircuitBreaker(3, 10*time.Second)
	assert.Equal(t, StateClosed, cb.GetState())
	assert.True(t, cb.CanExecute())
}

func TestCircuitBreaker_OpenAfterThreshold(t *testing.T) {
	cb := NewCircuitBreaker(3, 10*time.Second)

	// Record failures
	cb.RecordFailure()
	assert.Equal(t, StateClosed, cb.GetState())
	assert.True(t, cb.CanExecute())

	cb.RecordFailure()
	assert.Equal(t, StateClosed, cb.GetState())
	assert.True(t, cb.CanExecute())

	cb.RecordFailure()
	assert.Equal(t, StateOpen, cb.GetState())
	assert.False(t, cb.CanExecute())
}

func TestCircuitBreaker_HalfOpenAfterTimeout(t *testing.T) {
	cb := NewCircuitBreaker(2, 100*time.Millisecond)

	// Open the circuit
	cb.RecordFailure()
	cb.RecordFailure()
	assert.Equal(t, StateOpen, cb.GetState())
	assert.False(t, cb.CanExecute())

	// Wait for timeout
	time.Sleep(150 * time.Millisecond)

	// Should transition to half-open
	assert.True(t, cb.CanExecute())
	assert.Equal(t, StateHalfOpen, cb.GetState())
}

func TestCircuitBreaker_CloseAfterSuccessInHalfOpen(t *testing.T) {
	cb := NewCircuitBreaker(2, 100*time.Millisecond)

	// Open the circuit
	cb.RecordFailure()
	cb.RecordFailure()
	assert.Equal(t, StateOpen, cb.GetState())

	// Wait for timeout
	time.Sleep(150 * time.Millisecond)
	cb.CanExecute() // Transition to half-open

	// Record successes
	cb.RecordSuccess()
	cb.RecordSuccess()
	cb.RecordSuccess()

	// Should close after 3 successes
	assert.Equal(t, StateClosed, cb.GetState())
}

func TestCircuitBreaker_ReopenOnFailureInHalfOpen(t *testing.T) {
	cb := NewCircuitBreaker(2, 100*time.Millisecond)

	// Open the circuit
	cb.RecordFailure()
	cb.RecordFailure()
	assert.Equal(t, StateOpen, cb.GetState())

	// Wait for timeout
	time.Sleep(150 * time.Millisecond)
	cb.CanExecute() // Transition to half-open

	// Record failure in half-open state
	cb.RecordFailure()

	// Should reopen
	assert.Equal(t, StateOpen, cb.GetState())
	assert.False(t, cb.CanExecute())
}

func TestCircuitBreaker_ResetFailureCountOnSuccess(t *testing.T) {
	cb := NewCircuitBreaker(3, 10*time.Second)

	// Record some failures
	cb.RecordFailure()
	cb.RecordFailure()
	assert.Equal(t, StateClosed, cb.GetState())

	// Record success
	cb.RecordSuccess()

	// Failure count should be reset
	cb.RecordFailure()
	cb.RecordFailure()
	assert.Equal(t, StateClosed, cb.GetState()) // Still closed, not at threshold
}

func TestCircuitBreaker_Reset(t *testing.T) {
	cb := NewCircuitBreaker(2, 10*time.Second)

	// Open the circuit
	cb.RecordFailure()
	cb.RecordFailure()
	assert.Equal(t, StateOpen, cb.GetState())

	// Reset
	cb.Reset()

	// Should be closed
	assert.Equal(t, StateClosed, cb.GetState())
	assert.True(t, cb.CanExecute())
}
