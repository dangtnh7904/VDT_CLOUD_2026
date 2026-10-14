// One shared bound for all SSH exec channels, including background collectors.
// This does not claim to terminate remote processes on a timed-out connection.
export class CommandAdmission {
  constructor(limit = 4, maximumWaiting = 32) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 8
        || !Number.isInteger(maximumWaiting) || maximumWaiting < 0 || maximumWaiting > 128) {
      throw new Error('Invalid SSH command admission configuration');
    }
    this.limit = limit;
    this.maximumWaiting = maximumWaiting;
    this.active = 0;
    this.waiting = [];
  }

  acquire(timeout) {
    if (!Number.isFinite(timeout) || timeout <= 0) {
      return Promise.reject(Object.assign(new Error('Invalid SSH command deadline'), { code: 'EXECUTOR_NOT_CONFIGURED' }));
    }
    if (this.active < this.limit) {
      this.active += 1;
      return Promise.resolve(this.releaseToken());
    }
    if (this.waiting.length >= this.maximumWaiting) {
      return Promise.reject(Object.assign(new Error('SSH command queue is full'), { code: 'SSH_COMMAND_QUEUE_FULL' }));
    }
    return new Promise((resolve, reject) => {
      const entry = { resolve, reject, timer: null };
      entry.timer = setTimeout(() => {
        const index = this.waiting.indexOf(entry);
        if (index !== -1) this.waiting.splice(index, 1);
        reject(Object.assign(new Error('SSH command queue deadline exceeded'), { code: 'EXECUTOR_TIMEOUT' }));
      }, timeout);
      this.waiting.push(entry);
    });
  }

  releaseToken() {
    let released = false;
    return () => {
      if (released) return;
      released = true;
      const next = this.waiting.shift();
      if (next) {
        clearTimeout(next.timer);
        // Transfer the already-reserved slot; new arrivals cannot jump FIFO.
        next.resolve(this.releaseToken());
      } else {
        this.active -= 1;
      }
    };
  }
}
