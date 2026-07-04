import gym
import numpy as np
from gym import spaces
import pricing_engine
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback

class HestonCalibEnv(gym.Env):
    """
    Gym environment for calibrating Heston parameters [kappa, theta, xi, rho, v0]
    Action: continuous adjustments to each parameter
    Observation: current parameter values
    Reward: negative RMSE between model prices and market prices
    """
    metadata = {'render.modes': []}

    def __init__(self, strikes, market_prices, s0, r, tau):
        super().__init__()
        self.strikes = np.array(strikes)
        self.market = np.array(market_prices)
        self.s0, self.r, self.tau = s0, r, tau

        # Param bounds: kappa∈[0.1,5], theta∈[0.01,0.5], xi∈[0.1,1], rho∈[-0.9,0.0], v0∈[0.01,0.5]
        self.low  = np.array([0.1, 0.01, 0.1, -0.9, 0.01], dtype=np.float32)
        self.high = np.array([5.0, 0.5, 1.0,  0.0, 0.5 ], dtype=np.float32)
        self.action_space = spaces.Box(-0.1, 0.1, shape=(5,), dtype=np.float32)
        self.observation_space = spaces.Box(self.low, self.high, dtype=np.float32)

        # Initialize at mid-points
        self.state = (self.low + self.high) / 2

    def step(self, action):
        # Apply action and clip to bounds
        self.state = np.clip(self.state + action, self.low, self.high)

        # Unpack params
        kappa, theta, xi, rho, v0 = self.state
        # Compute Heston prices via Python binding (stubbed to 0.0, replace later)
        model_prices = []
        for K in self.strikes:
            c = pricing_engine.price_heston_call(
                self.s0, K, v0, self.r, kappa, theta, xi, rho, self.tau
            )
            model_prices.append(c)
        model_prices = np.array(model_prices)

        # Compute RMSE
        rmse = np.sqrt(np.mean((model_prices - self.market)**2))
        reward = -rmse

        done = False  # could add termination on small rmse or max steps
        info = {'rmse': rmse}

        return self.state.copy(), reward, done, info

    def reset(self):
        self.state = (self.low + self.high) / 2
        return self.state.copy()

    def render(self, mode='human'):
        pass
