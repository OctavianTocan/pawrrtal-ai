/**
 * Root layout: loads the brand fonts (Inter as the ABC Diatype interface-sans
 * stand-in, Lora for serif display, DM Mono for metadata), sets up the gesture
 * + safe-area providers, applies the dark status bar over the light theme, and
 * declares the navigation stack. Wraps everything in {@link RuntimeProvider} so
 * the Effect runtime is the outermost app concern.
 */
import { DMMono_400Regular, DMMono_500Medium } from '@expo-google-fonts/dm-mono';
import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  useFonts,
} from '@expo-google-fonts/inter';
import { Lora_600SemiBold, Lora_700Bold } from '@expo-google-fonts/lora';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { colors } from '@/constants/colors';
import { RuntimeProvider } from '@/runtime';

/** Shared light screen background for every route. */
const SCREEN_OPTIONS = {
  headerShown: false,
  contentStyle: { backgroundColor: colors.background },
} as const;

/** App root layout. */
export default function RootLayout(): React.JSX.Element | null {
  const [fontsLoaded] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
    Lora_600SemiBold,
    Lora_700Bold,
    DMMono_400Regular,
    DMMono_500Medium,
  });

  if (!fontsLoaded) {
    return null;
  }

  return (
    <RuntimeProvider>
      <GestureHandlerRootView style={styles.root}>
        <SafeAreaProvider>
          <StatusBar style="dark" />
          <Stack screenOptions={SCREEN_OPTIONS}>
            <Stack.Screen name="index" />
            <Stack.Screen name="conversation/[id]" />
            <Stack.Screen name="conversations" options={{ animation: 'slide_from_left' }} />
            <Stack.Screen name="settings" options={{ animation: 'slide_from_bottom' }} />
          </Stack>
        </SafeAreaProvider>
      </GestureHandlerRootView>
    </RuntimeProvider>
  );
}

const styles = {
  root: { flex: 1, backgroundColor: colors.background },
} as const;
