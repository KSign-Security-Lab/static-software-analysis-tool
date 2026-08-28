import com.ksign.sdb.api.KSSecurityFactory;
import com.ksign.sdb.api.SDBApi;
import com.ksign.sdb.api.config.APIConfig;

import java.io.*;
import java.util.HashMap;
import java.util.Map;

public class Sample {

	private static APIConfig config = null;
	private static SDBApi api = null;

	public Sample() {
		config = APIConfig.getInstance();
		config.setAgentHome("D:\\Jupiter_Agents\\Provider_patch\\SecureDBAgent.v3.6.1-1.0.5\\testAgent");
		System.out.println(String.format("Agent Home:: %s", config.getAppHome()));


		api = KSSecurityFactory.getInstance(config);
		System.out.println(String.format("deploy key size :: %d", api.loadKeyName().length));
		for (String policyName : api.loadKeyName()) {
			System.out.print(String.format(" [%s] ", policyName));
		}
		System.out.println("");

	}

	public static void main(String[] args) {
		Sample test = new Sample();
//		test.algTest();
//		test.ivTest();
		test.optionTest();
	}

	//		String enc = api.encrypt("test", "testLSH256");
//		System.out.println(String.format(":: enc[%s] ::", enc));
//
//		String enc2 = api.encrypt("test", "testLSH512");
//		System.out.println(String.format(":: enc[%s] ::", enc2));
//
//		String enc3 = api.encrypt("test", "LSH_256");
//		System.out.println(String.format(":: enc[%s] ::", enc3));
//
//		String enc4 = api.encrypt("test", "LSH_512");
//		System.out.println(String.format(":: enc[%s] ::", enc4));

	private void optionTest() {

		Map<String, String> encList = new HashMap<String, String>();
		String enc;
		String dec;
		String plainText = "SecureDB Test PlainText";
		int count = 0;
        System.out.println("==================================");
        for (String policyName : api.loadKeyName()) {
            try {
                enc = api.encrypt(plainText, policyName);
                System.out.print(String.format("  %s :: [%s] => [%s] =>", policyName, plainText, enc));
				encList.put(policyName, enc);
                dec = api.decrypt(enc, policyName);
                System.out.println(String.format(" [%s] ", dec));
            } catch (Exception e) {
                System.out.println("");
                count=count +1;
            }
        }
        System.out.println("==================================");
        System.out.println("Failed Count : " + count);

        //enc save // 1.0.3

		try {

			FileOutputStream fileOutputStream = new FileOutputStream("hashmap.ser");

			ObjectOutputStream objectOutputStream = new ObjectOutputStream(fileOutputStream);

			objectOutputStream.writeObject(encList);

			objectOutputStream.close();
			fileOutputStream.close();
			System.out.println("Enc List Saved");
		} catch (IOException e) {
			e.printStackTrace();
		}


		int enccount=0;
		int deccount=0;
		// saved enc compare // Fixed IV
//		try{
//			FileInputStream fileInputStream = new FileInputStream("hashmap.ser");
//			ObjectInputStream objectInputStream = new ObjectInputStream(fileInputStream);
//			Map<String, String> map = (HashMap<String, String>) objectInputStream.readObject();
//			objectInputStream.close();
//			fileInputStream.close();
//			System.out.println("==================================");
//			for (String policyName : api.loadKeyName()) {
//
//				try {
//					enc = api.encrypt(plainText, policyName);
//
//					if (enc.equals(map.get(policyName))){
//						System.out.print(String.format("Policy[%s] :: Encrypt[O] ", policyName));
//					}else{
//						System.out.print(String.format("Policy[%s] :: Encrypt[X] ", policyName));
//						System.out.println(policyName+" Encrypt Not Matched :: " + enc + " :: " + map.get(policyName));
//						enccount = enccount + 1;
//					}
//
//					dec = api.decrypt(enc, policyName);
//					if (dec.equals((plainText)) | dec.equals((map.get(policyName)))){
//						System.out.println(String.format("Decrypt[O] ::"));
//					}else{
//						System.out.println(String.format("Decrypt[X] ::"));
//						System.out.println(policyName + " Encrypt Not Matched :: " + dec + " :: " + map.get(policyName));
//						deccount = deccount + 1;
//					}
//				} catch (Exception e) {
//					System.out.println("");
//				}
//			}
//			System.out.println("==================================");
//		} catch (FileNotFoundException e) {
//			e.printStackTrace();
//		} catch (IOException | ClassNotFoundException e) {
//			e.printStackTrace();
//		}
//
//		System.out.println("ENC Failed Count : " + enccount);
//		System.out.println("DEC Failed Count : " + deccount);

		// saved enc compare // Record IV

//		count = 0;
//
//		try{
//			FileInputStream fileInputStream = new FileInputStream("hashmap.ser");
//			ObjectInputStream objectInputStream = new ObjectInputStream(fileInputStream);
//			Map<String, String> map = (HashMap<String, String>) objectInputStream.readObject();
//			objectInputStream.close();
//			fileInputStream.close();
//			System.out.println("==================================");
//			for (String policyName : api.loadKeyName()) {
//				try {
//					enc = api.encrypt(plainText, policyName);
//					if (!enc.equals(map.get(policyName))){
//						System.out.print(String.format("Policy[%s] :: Encrypt DIFF[O] ", policyName));
//					}else{
//						System.out.print(String.format("Policy[%s] :: Encrypt DIFF[X] ", policyName));
//						System.out.println(policyName+" Encrypt Not Matched :: " + enc + " :: " + map.get(policyName));
//					}
//
//					dec = api.decrypt(enc, policyName);
//					if (dec.equals((api.decrypt(map.get(policyName), policyName)))){
//						System.out.println(String.format("Decrypt[O] ::"));
//					}else{
//						System.out.println(String.format("Decrypt[X] ::"));
//						System.out.println(policyName + " Decrypt Not Matched :: " + dec + " :: " + api.decrypt(map.get(policyName), policyName));
//					}
//				} catch (Exception e) {
//					System.out.println("");
//					count = count + 1;
//				}
//			}
//			System.out.println("==================================");
//		} catch (FileNotFoundException e) {
//			e.printStackTrace();
//		} catch (IOException | ClassNotFoundException e) {
//			e.printStackTrace();
//		}
//		System.out.println("Failed Count : " + count);

	}


	private void ivTest() {
		//all alg Test [ Fixed IV, , Default options ]

		//Fixed IV values // Plain Text : "SecureDB Test PlainText"
		Map<String, String> encList = new HashMap<String, String>();
		encList.put("Fixed_ARIA_128", "$.O3ZVmvK+fdGm5vSn4ppOEFjXgt4q82uBL+NzVdpzvgU=");
		encList.put("Fixed_ARIA_256", "$.aleeI5CNYXR5kWNPiPXr6dtEDfKNOw92vrqmJtWIqls=");
		encList.put("Fixed_AES_128", "$.hrsxOz0DePRuI9AazjCMHnvMieC4HFNNJiqsYoT5v1g=");
		encList.put("Fixed_AES_256", "$.C39U7xpw9Bs8njessR0sQYnxQbdeErvOfHU0UtvFOiA=");
		encList.put("Fixed_SEED_128", "$.xAWETIb7AB28R2P+2Yn3DtUVKYtwjfqW0IOzKpLQsK0=");
		encList.put("Fixed_SHA_256", "$.tGkR7TJn56gwg4VVArEhxfGXBjuTHvwjcrxFIZL0g1g=");
		encList.put("Fixed_SHA_512", "$.yvTeiL+5RDdcByv9VlxzZhzAk0Q0jixBj9R+mK+M9XGQ1AxKwby/RJmbqEkkzuKzTviwrecmpPHaErT3qrCWjw==");
		encList.put("Fixed_LEA_128", "$.yXGYIWD3q7PXvcAfF3aXezjtYYcMzdzqroW6LgktDvM=");
		encList.put("Fixed_LEA_256", "$.JdtB1a7sAkTU5e3C0XGuRiI4hlkRV0p7RomT+wlv3b8=");
//		encList.put("Fixed_LSH_256", "$.7CvJbDaavHFLJ7h+ekWgMK8cOtxJ6UohHbDaWXXgT6s=");
//		encList.put("Fixed_LSH_512", "$.vsIj+58RleVxioNQCU6ZxDjtjHTmt3oOj8wchSHiw0RqBB5GeQLAFw7YwT34iwlNyaBNQz9Xk5YHcjQ6cTVwAw==");
		encList.put("Fixed_TDES_192", "$.l0RVU81KwWDf/7HUX6DrPQGbgSBGfzUL");
		encList.put("Fixed_SHA3_256", "$.InWZE06+MqB7D4/f1HoPQJcD6HRuWgOonv7vU4Yq4Zk=");
		encList.put("Fixed_SHA3_512", "$.JFPjPNKDV0FWmx9iJlUnXlBm6y5lZWWoKnrsOT9ZLzt12Ifop6eRPe9cvJhU+31eVip39mcdM3iM/9v+sYG0Yg==");

		encList.put("Record_ARIA_128", "$.xZLr4kcA4qAssYzGfEFBSxyiCznSd6oLI/iH03bLBolGdhPB");
		encList.put("Record_ARIA_256", "$.6z3zuwAGmmk4f+N9djJGKArmn03DuJCh8CBTp7AcpvNGR6gp");
		encList.put("Record_AES_128", "$.0pQn/wTSbv6EHqO3/mzs15vDSroi5hWLMXpXiz+jNNpGU6mZ");
		encList.put("Record_AES_256", "$.VUHfqe2U0DhOnOgzqvUt0nPuI2CpvwWQCXX3wfcxBIZGhG/t");
		encList.put("Record_SEED_128", "$.y3rolh0QAij1lfZMDnlZuMrGpbyEpEgNnCiuicNXr0BGcJ4Z");
		encList.put("Record_SHA_256", "$.tGkR7TJn56gwg4VVArEhxfGXBjuTHvwjcrxFIZL0g1g=");
		encList.put("Record_SHA_512", "$.yvTeiL+5RDdcByv9VlxzZhzAk0Q0jixBj9R+mK+M9XGQ1AxKwby/RJmbqEkkzuKzTviwrecmpPHaErT3qrCWjw==");
		encList.put("Record_LEA_128", "$.7WoOSlakw/VLl0naqr8pwuJTpnBfjXTceCbbmV3NKHVGgbfV");
		encList.put("Record_LEA_256", "$.3vEW687WRwXLOKb5CltfZ0g2y+4Gg/XufTeinpAnTR5GFO6d");
//		encList.put("Record_LSH_256", "$.7CvJbDaavHFLJ7h+ekWgMK8cOtxJ6UohHbDaWXXgT6s=");
//		encList.put("Record_LSH_512", "$.vsIj+58RleVxioNQCU6ZxDjtjHTmt3oOj8wchSHiw0RqBB5GeQLAFw7YwT34iwlNyaBNQz9Xk5YHcjQ6cTVwAw==");
		encList.put("Record_TDES_192", "$.7D4gMrlEAWxKnuoSmIaB7Xfpzg86kTlJRlz94Q==");
		encList.put("Record_SHA3_256", "$.InWZE06+MqB7D4/f1HoPQJcD6HRuWgOonv7vU4Yq4Zk=");
		encList.put("Record_SHA3_512", "$.JFPjPNKDV0FWmx9iJlUnXlBm6y5lZWWoKnrsOT9ZLzt12Ifop6eRPe9cvJhU+31eVip39mcdM3iM/9v+sYG0Yg==");

		String enc;
		String dec;
		String plainText = "SecureDB Test PlainText";

//		System.out.println("==================================");
//        for (String policyName : api.loadKeyName()) {
//
//            try {
//                enc = api.encrypt(plainText, policyName);
//                System.out.print(String.format("  %s :: [%s] => [%s] =>", policyName, plainText, enc));
//                dec = api.decrypt(enc, policyName);
//                System.out.println(String.format(" [%s] ", dec));
//            } catch (Exception e) {
//                System.out.println("");
//            }
//        }
//        System.out.println("==================================");

		//Compare with encList
		System.out.println("==================================");
		for (String policyName : api.loadKeyName()) {
			try {
				enc = api.encrypt(plainText, policyName);

				if (policyName.startsWith("Fixed")){
					if (enc.equals(encList.get(policyName))){
						System.out.print(String.format("Policy[%s] :: Encrypt Match[O] ", policyName));
					}else{
						System.out.print(String.format("Policy[%s] :: Encrypt Match[X] ", policyName));
					}

					dec = api.decrypt(enc, policyName);
					if (dec.equals((plainText))){
						System.out.println(String.format("Decrypt[O] ::"));
					}else{
						System.out.println(String.format("Decrypt[X] ::"));
					}
				}else{
					if (!enc.equals(encList.get(policyName))){
						System.out.print(String.format("Policy[%s] :: Encrypt Diff[O] ", policyName));
					}else{
						System.out.print(String.format("Policy[%s] :: Encrypt Diff[X] ", policyName));
					}
					dec = api.decrypt(enc, policyName);
					if (dec.equals((plainText))){
						System.out.println(String.format("Decrypt[O] ::"));
					}else{
						System.out.println(String.format("Decrypt[X] ::"));
					}
				}
			} catch (Exception e) {
				System.out.println("");
			}
		}
		System.out.println("==================================");
	}

	private void algTest() {

		//all alg Test [ Fixed IV, Default options ]


		// 1.0.3 Module En Decrypt Values // Plain Text : "SecureDB Test PlainText"
		Map<String, String> encList = new HashMap<String, String>();
		encList.put("ARIA_128", "$.U+tnPIgHR2sNJEpSPXprg0lb8Ot2sMZk9IIXu+9b908=");
		encList.put("ARIA_256", "$.NIu3GQRvWkOfk6CLZ5x2dVMLR6A2FUf04tbZVw05rsc=");
		encList.put("AES_128", "$.AvKu0VxwcNE2C2shl0JSN+n6ruiTXR29nQzs6KwNRMM=");
		encList.put("AES_256", "$.LGbNkUyr4N3AYCv2GqA63AhaPeSc8iImz6MfIX8ywj0=");
		encList.put("SEED_128", "$.2gRcuZvdaAUWiLmfcTO7tCvfsUmOG/M/Jk4Yj6N1kgQ=");
		encList.put("SHA_256", "$.tGkR7TJn56gwg4VVArEhxfGXBjuTHvwjcrxFIZL0g1g=");
		encList.put("SHA_512", "$.yvTeiL+5RDdcByv9VlxzZhzAk0Q0jixBj9R+mK+M9XGQ1AxKwby/RJmbqEkkzuKzTviwrecmpPHaErT3qrCWjw==");
		encList.put("LEA_128", "$.bnc6Y6dO8/zXgUJ8LL4uKdV9g2oczh5UhlBwGGR04EI=");
		encList.put("LEA_256", "$.5uEQB/Ju3/8INK2nGUKulz9/dKnTmJuPmYY2MN4C4VU=");
		encList.put("LSH_256", "$.Fu7PeKQFDZFxIKRXUMrqXNoBY9onSXuFtdk82UqK374=");
		encList.put("LSH_512", "$.PDKzlInD1/CuHzrcmmOv2X9TqnNwNKjlb6Vo10dz8zJb4pOPxBNYzMYMImqZv8GT0BSX6dSGCd9pAYQhhcbzag==");
		encList.put("TDES_192", "$.cK0fypzceyQjGm/FaG8M1WrDcVywt4PB");
		encList.put("SHA3_256", "$.InWZE06+MqB7D4/f1HoPQJcD6HRuWgOonv7vU4Yq4Zk="); //$.JFPjPNKDV0FWmx9iJlUnXlBm6y5lZWWoKnrsOT9ZLzs= similar 512
		encList.put("SHA3_512", "$.JFPjPNKDV0FWmx9iJlUnXlBm6y5lZWWoKnrsOT9ZLzt12Ifop6eRPe9cvJhU+31eVip39mcdM3iM/9v+sYG0Yg==");



		String enc;
		String dec;
		String plainText = "SecureDB Test PlainText";

//        System.out.println("==================================");
//        for (String policyName : api.loadKeyName()) {
//            try {
//                enc = api.encrypt(plainText, policyName);
//                System.out.print(String.format("  %s :: [%s] => [%s] =>", policyName, plainText, enc));
//                dec = api.decrypt(enc, policyName);
//                System.out.println(String.format(" [%s] ", dec));
//            } catch (Exception e) {
//                System.out.println("");
//            }
//        }
//        System.out.println("==================================");

		//Compare with encList
		System.out.println("==================================");
		for (String policyName : api.loadKeyName()) {
			try {
				enc = api.encrypt(plainText, policyName);
				if (enc.equals(encList.get(policyName))){
					System.out.print(String.format("Policy[%s] :: Encrypt[O] %s ", policyName, enc));

				}else{
//					System.out.print(String.format("Policy[%s] :: Encrypt[X] ", policyName));
					System.out.print(String.format("Policy[%s] :: Encrypt[O] %s ", policyName, enc));
				}
				System.out.println("");
//				dec = api.decrypt(enc, policyName);
//				if (dec.equals((plainText))){
//					System.out.println(String.format("Decrypt[O] ::"));
//				}else{
//					System.out.println(String.format("Decrypt[X] ::"));
//				}
			} catch (Exception e) {
				System.out.println("Encrypt Failed");
			}
		}
		System.out.println("==================================");


	}

}